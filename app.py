import os
import pyodbc
from dotenv import load_dotenv
from flask import request, session, redirect, url_for, render_template, flash
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_dance.contrib.google import make_google_blueprint, google
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from flask import jsonify, request
import logging
from flask import request, session, redirect, url_for, render_template, flash
from together import Together

load_dotenv()
# Initialize Together client with API key from environment variable
client = Together(api_key=os.getenv("TOGETHER_API_KEY"))
load_dotenv()

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key in production

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Example usage in a route or function:
# logger.info("This is an info message")
# logger.error("This is an error message")

# Google OAuth setup
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET"),
    scope=["profile", "email"],
    redirect_url="/google_login/authorized"
)
app.register_blueprint(google_bp, url_prefix="/login")

# Database connection function
def get_db_connection():
    conn = pyodbc.connect(
        f"DRIVER={os.environ['AZURE_SQL_DRIVER']};"
        f"SERVER={os.environ['AZURE_SQL_SERVER']};"
        f"DATABASE={os.environ['AZURE_SQL_DATABASE']};"
        f"UID={os.environ['AZURE_SQL_USERNAME']};"
        f"PWD={os.environ['AZURE_SQL_PASSWORD']}"
    )
    return conn

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, phone_number, password, is_active, role) VALUES (?, ?, ?,?, ?, ?)",
                (username, email, phone, hashed_password, 1, 'user')
            )
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except Exception as e:
            error = 'Registration failed: ' + str(e)
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password, is_active FROM users WHERE username = ?",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()
        if user:
            stored_password, is_active = user
            if is_active and check_password_hash(stored_password, password):
                session['username'] = username
                return redirect(url_for('dashboard'))
            elif not is_active:
                error = 'Account is inactive.'
            else:
                error = 'Invalid username or password.'
        else:
            error = 'Invalid username or password.'
    return render_template('login.html', error=error)

@app.route('/google_login')
def google_login():
    if not google.authorized:
        return redirect(url_for('google.login'))
    resp = google.get("/oauth2/v2/userinfo")
    assert resp.ok, resp.text
    user_info = resp.json()
    session['username'] = user_info['email']
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET last_login = ? WHERE username = ?",
            (datetime.now(), username)
        )
        conn.commit()
        conn.close()
        session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    data = request.get_json()
    email = data.get('email')
    phone = data.get('phone')
    comments = data.get('comments')
    rating = data.get('rating', -1)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO feedback (email, name, comments, rating)
            VALUES (?, ?, ?, ?)
        """, (email, phone, comments, rating))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Feedback submitted!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/submit-problem', methods = ['GET','POST'])
def submit_problem():
    error = None
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST' and request.form.get('action') == 'get_solution':
        title = request.form.get('title','NA')
        description = request.form.get('problem','NA')
        priority = request.form.get('priority', 'medium')
        category = request.form.get('category','NA')

        # Get user id from username
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
        user = cursor.fetchone()
        if not user:
            conn.close()
            error = "User not found."
            return render_template('submit_problem.html', error=error)

        created_by = user.id

        try:
            cursor.execute(
                """
                INSERT INTO problems (title, description, created_by, priority, category)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, description, created_by, priority, category)
            )
            
            flash('Problem submitted successfully!')
            # Get the problem id of the newly inserted problem
            cursor.execute("SELECT id FROM problems WHERE description = ? AND created_by = ? ORDER BY id DESC", (description, created_by))
            problem_row = cursor.fetchone()
            conn.commit()
            conn.close()
            if problem_row:
                problem_id = problem_row[0]
            else:
                error = "Could not retrieve the newly created problem ID."
                return render_template('submit_problem.html', error=error)
            return redirect(url_for('get_relevant_solution_ids', problem_id=problem_id))  # this should redirect to the most probable solutions for this problem
        except Exception as e:
            conn.close()
            error = "Failed to submit problem: " + str(e)
    return render_template('submit_problem.html', error=error)

@app.route('/view-problems', methods=['GET'])
def view_all_problems():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT p.id, p.title, p.description, p.category, u.username
    FROM problems p
    JOIN users u ON p.created_by = u.id
    ORDER BY p.id DESC
    """)
    problems = cursor.fetchall()
    conn.close()
    return render_template('view_problems.html', problems=problems)

@app.route('/view-problems/<int:problem_id>', methods=['GET'])
def view_single_problem(problem_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id, p.description, p.category, u.username, p.links, u.email, u.phone_number
        FROM problems p
        JOIN users u ON p.created_by = u.id
        WHERE p.id = ?
    """, (problem_id,))
    problem = cursor.fetchone()
    conn.close()
    return render_template('problem_detail.html', problem=problem, problem_id=problem_id)


    error = None
    if 'username' not in session:
        logger.warning("Unauthorized access attempt to submit_solution.")
        return redirect(url_for('login'))

    if request.method == 'POST' and request.form.get('action') == 'submit_solution':
        logger.info(f"User '{session.get('username')}' is submitting a solution.")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Get next solution ID
            cursor.execute("SELECT MAX(id) FROM solutions")
            max_id_row = cursor.fetchone()
            next_id = (max_id_row[0] or 0) + 1
            logger.debug(f"Next solution ID calculated as {next_id}.")

            # Get user id from username
            cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
            user = cursor.fetchone()
            if not user:
                logger.error(f"User '{session.get('username')}' not found in database.")
                error = "User not found."
                return render_template('submit_solution.html', error=error)

            created_by = user[0]
            description = request.form.get('description')
            remarks = request.form.get('remarks', 'NA')
            status = request.form.get('status', 'pending')
            category = request.form.get('category', 'general')
            links = request.form.get('link', 'NA') 

            logger.info(f"Inserting solution by user_id={created_by}.")
            cursor.execute(
                """
                INSERT INTO solutions (id, description, category, created_by, status, remarks, links, problem_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (next_id, description, category, created_by, status, remarks, links, problem_id)
            )
            conn.commit()
            logger.info(f"Solution {next_id} submitted successfully by user_id={created_by}.")
            flash('Solution submitted successfully!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.exception("Failed to submit solution.")
            error = "Failed to submit solution: " + str(e)
        finally:
            conn.close()
            logger.debug("Database connection closed after submit_solution.")
    return render_template('submit_solution.html', error=error)

@app.route('/submit-solution', methods=[ 'GET', 'POST'])
def submit_solution(): 
    error = None
    if 'username' not in session:
        logger.warning("Unauthorized access attempt to submit_solution.")
        return redirect(url_for('login'))

    if request.method == 'POST' and request.form.get('action') == 'submit_solution':
        logger.info(f"User '{session.get('username')}' is submitting a solution.")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Get next solution ID
            cursor.execute("SELECT MAX(id) FROM solutions")
            max_id_row = cursor.fetchone()
            next_id = (max_id_row[0] or 0) + 1
            logger.debug(f"Next solution ID calculated as {next_id}.")

            # Use problem_id from the function parameter (from the URL path)
            # No need to fetch from form or elsewhere, just use the provided problem_id

            # Get user id from username
            cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
            user = cursor.fetchone()
            if not user:
                logger.error(f"User '{session.get('username')}' not found in database.")
                error = "User not found."
                return render_template('submit_solution.html', error=error)
           
            created_by = user[0]
            description = request.form.get('description')
            remarks = request.form.get('remarks', 'NA')
            status = request.form.get('status', 'pending')
            category = request.form.get('category', 'general')
            links = request.form.get('link', 'NA') 
            # print(created_by, description, category, status, remarks, links, problem_id)
            logger.info(f"Inserting solution by user_id={created_by}.")
            cursor.execute(
                """
                INSERT INTO solutions (id, description, category, created_by, status, remarks, links )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (next_id, description, category, created_by, status, remarks, links )
            )
            conn.commit()
            logger.info(f"Solution {next_id} submitted successfully by user_id={created_by}.")
            flash('Solution submitted successfully!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.exception("Failed to submit solution.")
            error = "Failed to submit solution: " + str(e)
        finally:
            conn.close()
            logger.debug("Database connection closed after submit_solution.")
    return render_template('submit_solution.html', error=error)

@app.route('/submit-solution/<int:problem_id>', methods=['GET', 'POST']) 
def submit_solution_pid(problem_id):
    error = None
    if 'username' not in session:
        logger.warning("Unauthorized access attempt to submit_solution.")
        return redirect(url_for('login'))

    if request.method == 'POST' and request.form.get('action') == 'submit_solution':
        logger.info(f"User '{session.get('username')}' is submitting a solution.")
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Get next solution ID
            cursor.execute("SELECT MAX(id) FROM solutions")
            max_id_row = cursor.fetchone()
            next_id = (max_id_row[0] or 0) + 1
            logger.debug(f"Next solution ID calculated as {next_id}.")

            # Use problem_id from the function parameter (from the URL path)
            # No need to fetch from form or elsewhere, just use the provided problem_id

            # Get user id from username
            cursor.execute("SELECT id FROM users WHERE username = ?", (session['username'],))
            user = cursor.fetchone()
            if not user:
                logger.error(f"User '{session.get('username')}' not found in database.")
                error = "User not found."
                return render_template('submit_solution.html', error=error)
            print(problem_id)
            created_by = user[0]
            description = request.form.get('description')
            remarks = request.form.get('remarks', 'NA')
            status = request.form.get('status', 'pending')
            category = request.form.get('category', 'general')
            links = request.form.get('link', 'NA') 
            # print(created_by, description, category, status, remarks, links, problem_id)
            logger.info(f"Inserting solution by user_id={created_by}.")
            cursor.execute(
                """
                INSERT INTO solutions (id, description, category, created_by, status, remarks, links, problem_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (next_id, description, category, created_by, status, remarks, links, problem_id)
            )
            conn.commit()
            logger.info(f"Solution {next_id} submitted successfully by user_id={created_by}.")
            flash('Solution submitted successfully!')
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.exception("Failed to submit solution.")
            error = "Failed to submit solution: " + str(e)
        finally:
            conn.close()
            logger.debug("Database connection closed after submit_solution.")
    return render_template('submit_solution.html', error=error, problem_id=problem_id)

@app.route('/view-solutions', methods=['GET'])
def view_all_solutions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.description, s.category, u.username, s.id, s.problem_id
        FROM solutions s
        JOIN users u ON s.created_by = u.id
        ORDER BY s.created_at DESC
        """)
    solutions = cursor.fetchall()
    conn.close()
    print("Solutions fetched:", solutions)
    return render_template('view_solutions.html', solutions=solutions)
    
@app.route('/view-solutions/<int:solution_id>', methods=['GET'])
def view_single_solution(solution_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.description, s.category, u.username, s.id, s.problem_id, u.phone_number, u.email
        FROM solutions s
        JOIN users u ON s.created_by = u.id
        WHERE s.id = ?
    """, (solution_id,))
    solution = cursor.fetchone()
    conn.close()
    if solution:
        return render_template('solution_detail.html', solution=solution)
    flash('Solution not found.', 'danger')
    return redirect(url_for('view_solutions'))
    
@app.route('/view-solutions/<int:solution_id>/star', methods=['POST'])
def star_solution(solution_id):
    data = request.get_json()
    starred = data.get('starred', True)  # Default to True if not provided

    conn = get_db_connection()
    cursor = conn.cursor()

    if starred:
        # Increment star count
        cursor.execute("""
            UPDATE solutions
            SET stars = stars + 1
            WHERE id = ?
        """, (solution_id,))
    else:
        # Decrement star count, prevent going below 0
        cursor.execute("""
            UPDATE solutions
            SET stars = CASE WHEN stars > 0 THEN stars - 1 ELSE 0 END
            WHERE id = ?
        """, (solution_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'starred': starred})

@app.route('/view-solutions/<int:solution_id>/like', methods=['POST'])
def like_solution(solution_id):
    data = request.get_json()
    liked = data.get('liked', True)  # defaults to True if not present

    conn = get_db_connection()
    cursor = conn.cursor()

    if liked:
        # Increment likes
        cursor.execute("""
            UPDATE solutions
            SET likes = likes + 1
            WHERE id = ?
        """, (solution_id,))
    else:
        # Decrement likes, but don’t allow negative values
        cursor.execute("""
            UPDATE solutions
            SET likes = CASE WHEN likes > 0 THEN likes - 1 ELSE 0 END
            WHERE id = ?
        """, (solution_id,))

    conn.commit()
    conn.close()

    return jsonify({'success': True, 'liked': liked})

@app.route('/view-solutions/<int:problem_id>/submit-link', methods=['POST'])
def submit_link(problem_id):
    solution_link = request.form.get('solution_link')
    print(problem_id, solution_link)
    if not problem_id or not solution_link:
        flash('Problem ID and Solution Link are required.', 'danger')
        return redirect(url_for('view_problems'))

    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch existing links
    cursor.execute("SELECT links FROM problems WHERE id = ?", (problem_id,))
    row = cursor.fetchone()
    if row:
        existing_links = row[0] or ''
        # Concatenate new link (comma-separated)
        if existing_links.strip():
            updated_links = existing_links.strip() + ',' + solution_link.strip()
        else:
            updated_links = solution_link.strip()
        cursor.execute("UPDATE problems SET links = ? WHERE id = ?", (updated_links, problem_id))
        conn.commit()
        flash('Solution link added successfully!', 'success')
    else:
        flash('Problem not found.', 'danger')
    conn.close()
    return redirect(url_for('view_single_problem', problem_id=problem_id))

@app.route('/view-relevant-solutions/<int:problem_id>', methods=['GET', 'POST'])
def get_relevant_solution_ids(problem_id):
    """
    Calls Together LLM to find relevant solution IDs for a given problem.
    
    Args:
        problem (dict): A dictionary with problem details (should include 'category', 'description', etc.).
        solutions (list): A list of dictionaries, each with solution details (should include 'id', 'category', 'description', etc.).
    
    Returns:
        list: List of relevant solution IDs (ints or strings).
    """
    # Prepare the prompt for the LLM
    if problem_id:
        conn = get_db_connection()  
        cursor = conn.cursor()
        #fetch username from user table by joining created_by from problems table
        cursor.execute("SELECT p.category, p.description, u.username FROM problems p JOIN users u ON p.created_by = u.id WHERE p.id = ?", (problem_id,))
        problem = cursor.fetchone()
        problem = dict(zip([column[0] for column in cursor.description], problem))
        print(problem)
    if problem:
        # cursor.execute("SELECT id, category, description FROM solutions WHERE problem_id = ?", (problem_id,))
        cursor.execute("SELECT id, category, description FROM solutions")
        solutions = cursor.fetchall()
        solutions = [dict(zip([column[0] for column in cursor.description], solution)) for solution in solutions]
        print(solutions)
        conn.close()

    prompt = (
        "Given the following problem and a list of solutions, "
        "return a Python list of the IDs of the solutions that are most relevant to the problem. "
        "Return only a Python list of the IDs of the relevant solutions ranked from highly relevant to least relevant. Do not include any explanation or extra text. Example: [1, 2, 3]"
        "Only include the IDs, nothing else.\n\n"
        f"Problem: {problem}\n\n"
        f"Solutions: {solutions}\n\n"
        "Relevant solution IDs:"
    )
    print(solutions)
    messages = [
        {"role": "user", "content": prompt}
    ]
    try:
        response = client.chat.completions.create(
            model="meta-llama/Meta-Llama-3-8B-Instruct-Reference",
            messages=messages,
            temperature=0.2,
            max_tokens=64,
            top_p=0.9,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            stop=None,
            stream=False,
            n=1
        )
        # The LLM should return a Python list of IDs, e.g., [1, 3, 5]
        # print(response)
        if not response.choices or not response.choices[0].message.content:
            print("No content returned from LLM.")
            return []
        content = response.choices[0].message.content.strip()
        # Safely evaluate the list from the string
        # print("LLM response content:", content)
        relevant_ids = eval(content, {"__builtins__": {}})
        # print("Relevant IDs:", relevant_ids)
        if isinstance(relevant_ids, list):
            print("Relevant solution IDs:", relevant_ids)  
            conn = get_db_connection()
            cursor = conn.cursor()
            # Prepare a parameterized query for the relevant IDs
            if relevant_ids:
                placeholders = ','.join(['?'] * len(relevant_ids))
                cursor.execute(
                    f"""SELECT s.id, s.description, s.category, u.username,s.links FROM solutions s
                    JOIN users u ON s.created_by = u.id
                    WHERE s.id IN ({placeholders})""", relevant_ids)
                matched_solutions = cursor.fetchall()
                conn.close()
                # Optionally, you can return these solutions as JSON or use them as needed
                return render_template('relevant_solutions.html', relevant_ids=relevant_ids, solutions=matched_solutions, problem=problem)
            else:
                conn.close()
                return render_template('relevant_solutions.html', relevant_ids=[], solutions=[], problem=problem) 
            return  render_template('relevant_solutions.html', relevant_ids=relevant_ids, solutions=matched_solutions, problem=problem) 
        else:
            return render_template('relevant_solutions.html', relevant_ids=[], solutions=[], problem=problem)
    except Exception as e:
        print("Error in get_relevant_solution_ids:", e)
        return render_template('relevant_solutions.html', relevant_ids=[], solutions=[], problem=problem) 

@app.route('/view-relevant-problems/<int:solution_id>', methods=['GET', 'POST'])
def view_relevant_problems(solution_id):
    # Prepare the prompt for the LLM
    if solution_id:
        conn = get_db_connection()  
        cursor = conn.cursor()
        #fetch username from user table by joining created_by from problems table
        cursor.execute("SELECT p.category, p.description, u.username FROM solutions p JOIN users u ON p.created_by = u.id WHERE p.id = ?", (solution_id,))
        solution = cursor.fetchone()
        solution = dict(zip([column[0] for column in cursor.description], solution))
        
    if solution:
        # cursor.execute("SELECT id, category, description FROM solutions WHERE problem_id = ?", (problem_id,))
        cursor.execute("SELECT id, category, description FROM problems")
        problems = cursor.fetchall()
        problems = [dict(zip([column[0] for column in cursor.description], problem)) for problem in problems]
        
        conn.close()

    prompt = (
        "Given the following solution and a list of problems, "
        "return a Python list of the IDs of the problems that are most relevant and can be solved using the solution. Description and category columns contain the most important information to match the problems to the solution.\n"
        "Return only a Python list of the IDs of the relevant problems ranked from highly relevant to least relevant. Do not include any explanation or extra text. Example: [1, 2, 3]"
        "Only include the IDs, nothing else.\n\n"
        f"Solution: {solution}\n\n"
        f"Problems: {problems}\n\n"
        "Relevant problem IDs:"
    )
    messages = [
        {"role": "user", "content": prompt}
    ]
    try:
        response = client.chat.completions.create(
            model="lgai/exaone-3-5-32b-instruct",
            messages=messages,
            temperature=0.2,
            max_tokens=64,
            top_p=0.9,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            stop=None,
            stream=False,
            n=1
        )
        # The LLM should return a Python list of IDs, e.g., [1, 3, 5]
        # print(response)
        if not response.choices or not response.choices[0].message.content:
            print("No content returned from LLM.")
            return []
        content = response.choices[0].message.content.strip()
        # Safely evaluate the list from the string
        relevant_ids = eval(content, {"__builtins__": {}})
        # print("Relevant IDs:", relevant_ids)
        if isinstance(relevant_ids, list):
            print("Relevant problem IDs:", relevant_ids)
            conn = get_db_connection()
            cursor = conn.cursor()
            # Prepare a parameterized query for the relevant IDs
            if relevant_ids:
                placeholders = ','.join(['?'] * len(relevant_ids))
                cursor.execute(
                    f"""SELECT s.id, s.description, s.category, u.username,s.links FROM problems s
                    JOIN users u ON s.created_by = u.id
                    WHERE s.id IN ({placeholders})""", relevant_ids)
                matched_problems = cursor.fetchall()
                conn.close()
                # Optionally, you can return these problems as JSON or use them as needed
                return render_template('relevant_problems.html', relevant_ids=relevant_ids, problems=matched_problems, solution=solution)
            else:
                conn.close()
                return render_template('relevant_problems.html', relevant_ids=[], problems=[], solution=solution)
        else:
            return render_template('relevant_problems.html', relevant_ids=[], problems=[], solution=solution)
    except Exception as e:
        print("Error in get_relevant_problem_ids:", e)
        return render_template('relevant_problems.html', relevant_ids=[], problems=[], solution=solution)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
