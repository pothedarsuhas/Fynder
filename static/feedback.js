// Floating Feedback Button and Chatbox Logic
(function() {
    const btn = document.createElement('button');
    btn.id = 'feedback-btn';
    btn.innerText = 'Provide Feedback';
    document.body.appendChild(btn);

    const chatbox = document.createElement('div');
    chatbox.id = 'feedback-chatbox';
    chatbox.innerHTML = `
        <div id="feedback-chatbox-header">
            Feedback
            <button id="feedback-chatbox-close" title="Close">&times;</button>
        </div>
        <div id="feedback-chatbox-body">
            <input id="feedback-email" type="email" placeholder="Your email (required)" style="width:100%;margin-bottom:10px;padding:8px;border-radius:8px;border:1px solid #e5e7eb;font-size:1rem;" required />
            <input id="feedback-phone" type="tel" placeholder="Your phone number (optional)" style="width:100%;margin-bottom:10px;padding:8px;border-radius:8px;border:1px solid #e5e7eb;font-size:1rem;" pattern="^\\+?[0-9\\s\\-]{7,15}$" />
            <textarea id="feedback-chatbox-text" placeholder="Let us know your thoughts, suggestions, or issues..." required></textarea>
        </div>
        <div id="feedback-chatbox-footer">
            <button id="feedback-chatbox-submit">Submit</button>
        </div>
    `;
    document.body.appendChild(chatbox);

    btn.addEventListener('click', function() {
        chatbox.classList.add('active');
        setTimeout(() => {
            document.getElementById('feedback-email').focus();
        }, 100);
    });
    document.getElementById('feedback-chatbox-close').onclick = function() {
        chatbox.classList.remove('active');
        document.getElementById('feedback-email').value = '';
        document.getElementById('feedback-phone').value = '';
        document.getElementById('feedback-chatbox-text').value = '';
    };

    // Submit button handler
    document.getElementById('feedback-chatbox-submit').onclick = function() {
        const email = document.getElementById('feedback-email').value.trim();
        const phone = document.getElementById('feedback-phone').value.trim();
        const text = document.getElementById('feedback-chatbox-text').value.trim();

        // Email validation
        const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!email) {
            alert('Please enter your email.');
            document.getElementById('feedback-email').focus();
            return;
        }
        if (!emailPattern.test(email)) {
            alert('Please enter a valid email address.');
            document.getElementById('feedback-email').focus();
            return;
        }

        // Phone validation (optional, but if present, must be valid)
        if (phone) {
            const phonePattern = /^\+?[0-9\s\-]{7,15}$/;
            if (!phonePattern.test(phone)) {
                alert('Please enter a valid phone number.');
                document.getElementById('feedback-phone').focus();
                return;
            }
        }

        if (!text) {
            alert('Please enter your feedback.');
            document.getElementById('feedback-chatbox-text').focus();
            return;
        }

        // Submit feedback via AJAX
        fetch('/submit_feedback', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                email: email,
                phone: phone,
                comments: text
            })
        })
        .then(res => res.json())
        .then(response => {
            if(response.success){
                alert('Thank you for your feedback!');
                // Clear fields
                document.getElementById('feedback-email').value = '';
                document.getElementById('feedback-phone').value = '';
                document.getElementById('feedback-chatbox-text').value = '';
                // Close the floating feedback
                chatbox.classList.remove('active');
            } else {
                alert('Error: ' + response.message);
            }
        })
        .catch(err => {
            alert('Error: ' + err);
        });
    };
})();
