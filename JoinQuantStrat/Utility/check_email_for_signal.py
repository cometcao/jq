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

def search_emails(mail):
    status, messages = mail.search(None, "Unseen")
    if status != "OK":
        print("Failed to search for unseen emails")
    return messages[0].split()

def fetch_latest_email(mail, email_ids, target_subject):
    latest_email_id = None
    latest_email_date = None
    latest_msg_data = None

    for email_id in email_ids:
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            continue
        
        msg = email.message_from_bytes(msg_data[0][1])
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        
        if target_subject in subject:
            date = msg["Date"]
            msg_date = datetime.strptime(date[:25], "%a, %d %b %Y %H:%M:%S")
            
            if latest_email_date is None or msg_date > latest_email_date:
                latest_email_id = email_id
                latest_email_date = msg_date
                latest_msg_data = msg_data

    if latest_email_id is None:
        print(f"No emails found with subject '{target_subject}'")

    return latest_email_id, latest_msg_data

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

def check_email_and_save_attachment(config):
    try_count = 0
    max_retries = 3
    while try_count < max_retries:
        now = datetime.now()
        try_count += 1
        try:
            mail = connect_to_mail_server(config['imap_server'], config['email_user'], config['email_pass'])
            select_mailbox(mail, "INBOX") # Ensure the mailbox is selected before searching
            email_ids = search_emails(mail)
            
            if not email_ids:
                print(f"current time: {now} No unseen emails found.")
                continue
            
            latest_email_id, msg_data = fetch_latest_email(mail, email_ids, config['target_subject'])
            process_email(msg_data, config['save_directory'])
            
            mail.store(latest_email_id, "+FLAGS", "\\Deleted")
            mail.expunge()
            mail.logout()
            break  # Exit the loop if successful
        except imaplib.IMAP4.error as e:
            print(f"IMAP error: {e}")
            traceback.print_exc()
        except FileNotFoundError as e:
            print(f"File not found: {e}")
            traceback.print_exc()
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            traceback.print_exc()
        finally:
            print(f"current time: {now} Retrying... ({try_count}/{max_retries})")
            time.sleep(10)  # Wait for 10 seconds before retrying

def run_daily_at_specific_time(config_filename):
    config = load_config(config_filename)
    run_time = config["run_time"]
    while True:
        if not run_time:
            check_email_and_save_attachment(config)
        else:
            now = datetime.now()
            target_time = datetime.strptime(run_time, "%H:%M").replace(year=now.year, month=now.month, day=now.day)

            if now > target_time:
                target_time += timedelta(days=1)

            sleep_duration = (target_time - now).total_seconds()
            print(f"current time: {now} Sleeping for {sleep_duration} seconds until next run at {target_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            time.sleep(sleep_duration)
            
            check_email_and_save_attachment(config)

if __name__ == "__main__":
    config_filename = "email_reader_config.json"
    run_daily_at_specific_time(config_filename)