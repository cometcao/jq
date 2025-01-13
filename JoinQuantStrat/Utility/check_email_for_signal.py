import imaplib
import email
from email.header import decode_header
import os
import json
import time
from datetime import datetime, timedelta
import traceback

def load_config(config_filename):
    with open(config_filename, 'r') as f:
        return json.load(f)

def connect_to_mail_server(imap_server, email_user, email_pass):
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(email_user, email_pass)
    imaplib.Commands["ID"] = ('AUTH',)
    args = ("name", email_user, "contact", email_user, "version", "1.0.0", "vendor", "myclient")
    mail._simple_command("ID", str(args).replace(",", "").replace("\'", "\""))
    return mail

def select_mailbox(mail, mailbox="INBOX"):
    status, _ = mail.select(mailbox, readonly=False)
    if status != "OK":
        raise Exception(f"Failed to select mailbox '{mailbox}'")

def search_emails(mail, target_subject):
    today = datetime.now().strftime("%d-%b-%Y")
    status, messages = mail.search(None, f'(SUBJECT "{target_subject}" SINCE {today})')
    # status, messages = mail.search(None, "Unseen")
    if status != "OK":
        print(messages)
        raise Exception(f"Failed to search emails with subject '{target_subject}' received today")
    return messages[0].split()

def fetch_latest_email(mail, email_ids):
    latest_email_id = email_ids[-1]
    status, msg_data = mail.fetch(latest_email_id, "(RFC822)")
    if status != "OK":
        raise Exception(f"Failed to fetch email ID {latest_email_id}")
    return latest_email_id, msg_data

def process_email(msg_data, save_directory):
    for response_part in msg_data:
        if isinstance(response_part, tuple):
            msg = email.message_from_bytes(response_part[1])
            subject, encoding = decode_header(msg["Subject"])[0]
            if isinstance(subject, bytes):
                subject = subject.decode(encoding if encoding else "utf-8")
            if msg.is_multipart():
                for part in msg.walk():
                    content_disposition = part.get("Content-Disposition", None)
                    if content_disposition:
                        dispositions = content_disposition.strip().split(";")
                        if "attachment" in dispositions:
                            filename = part.get_filename()
                            if filename:
                                filepath = os.path.join(save_directory, filename)
                                with open(filepath, "wb") as f:
                                    f.write(part.get_payload(decode=True))
                                print(f"Attachment saved: {filepath}")

def check_email_and_save_attachment(config_filename):
    try_count = 0
    max_retries = 3
    while try_count < max_retries:
        try:
            config = load_config(config_filename)
            mail = connect_to_mail_server(config['imap_server'], config['email_user'], config['email_pass'])
            select_mailbox(mail, "INBOX")  # Ensure the mailbox is selected before searching
            email_ids = search_emails(mail, config['target_subject'])
            
            if not email_ids:
                print("No emails found for today.")
                raise Exception("No emails found for today.")
            
            latest_email_id, msg_data = fetch_latest_email(mail, email_ids)
            process_email(msg_data, config['save_directory'])
            
            mail.store(latest_email_id, "+FLAGS", "\\Deleted")
            mail.expunge()
            mail.logout()
            break  # Exit the loop if successful
        except imaplib.IMAP4.error as e:
            print(f"IMAP error: {e}")
        except FileNotFoundError as e:
            print(f"File not found: {e}")
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            # traceback.print_exc()
        finally:
            try_count += 1
        print(f"Retrying... ({try_count}/{max_retries})")
        time.sleep(10)  # Wait for 10 seconds before retrying

def run_daily_at_specific_time(config_filename, run_time=None):
    while True:
        if run_time is None:
            check_email_and_save_attachment(config_filename)
        else:
            now = datetime.now()
            target_time = datetime.strptime(run_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)

            if now > target_time:
                target_time += timedelta(days=1)

            sleep_duration = (target_time - now).total_seconds()
            print(f"Sleeping for {sleep_duration} seconds until next run at {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            time.sleep(sleep_duration)
            
            check_email_and_save_attachment(config_filename)

if __name__ == "__main__":
    config = {
        "imap_server": "imap.163.com",
        "email_user": "17317768857@163.com",
        "email_pass": "DJiYmKrzUj842sg8",
        "save_directory": ".",
        "target_subject": "TTC1"
    }

    config_filename = "config.json"
    
    with open(config_filename, 'w') as f:
        json.dump(config, f)

    os.makedirs(config['save_directory'], exist_ok=True)

    run_time = None
    run_daily_at_specific_time(config_filename, run_time)