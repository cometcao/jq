import simplejson as json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders

def save_list_as_json(data, filename):
    with open(filename, 'w') as f:
        json.dump(data, f)

def send_email_with_attachment(email_config_filename, attachment_filename):
    # Load email configuration from JSON file
    with open(email_config_filename, 'r') as f:
        email_config = json.load(f)
    
    sender_email = email_config['sender_email']
    sender_password = email_config['sender_password']
    receiver_email = email_config['receiver_email']
    subject = email_config['subject']
    body = email_config['body']
    smtp_address = email_config["smtp_address"]
    smtp_port = email_config["smtp_port"]

    # Create a multipart message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject

    # Attach the body with the msg instance
    msg.attach(MIMEText(body, 'plain'))

    # Open the file to be sent
    with open(attachment_filename, 'rb') as attachment:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(attachment.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename= {attachment_filename}')
        msg.attach(part)

    # Create SMTP session for sending the mail
    with smtplib.SMTP(smtp_address, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        try:
            server.sendmail(sender_email, receiver_email, text)
            print("Email sent")
        except:
            print("Email failed")
# Example usage:
# data = ["string1", "string2", "string3"]

# email_config_filename = "email_config.json"
# data_json_file = "email_test.json"
# save_list_as_json(data, data_json_file)

# send_email_with_attachment(email_config_filename)