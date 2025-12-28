from flask_mail import Message
from flask import current_app, render_template
from extensions import mail

def send_email(to, subject, template, **kwargs):
    app = current_app._get_current_object()
    msg = Message(
        subject,
        sender=app.config['MAIL_USERNAME'],
        recipients=[to]
    )
    msg.body = render_template(template + '.txt', **kwargs)
    msg.html = render_template(template + '.html', **kwargs)
    try:
        mail.send(msg)
        print(f"Email successfully sent to {to}")
    except Exception as e:
        print(f"Error sending email to {to}: {e}")