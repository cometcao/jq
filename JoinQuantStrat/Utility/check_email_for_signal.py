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

def fetch_latest_emails(mail, email_ids, target_subjects):
    """For each target subject, find the latest matching email.
    Returns a list of (email_id, msg_data) tuples, one per matched subject."""
    results = {}  # subject -> (email_id, email_date, msg_data)

    for email_id in email_ids:
        status, msg_data = mail.fetch(email_id, "(RFC822)")
        if status != "OK":
            continue

        msg = email.message_from_bytes(msg_data[0][1])
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")

        for target_subject in target_subjects:
            if target_subject in subject:
                date = msg["Date"]
                msg_date = datetime.strptime(date[:24], "%a, %d %b %Y %H:%M:%S")

                if target_subject not in results or msg_date > results[target_subject][1]:
                    results[target_subject] = (email_id, msg_date, msg_data)

    for target_subject in target_subjects:
        if target_subject not in results:
            print(f"No emails found with subject '{target_subject}'")

    return [(r[0], r[2]) for r in results.values()]

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
    target_subjects = config['target_subject']
    if isinstance(target_subjects, str):
        target_subjects = [target_subjects]

    try_count = 0
    max_retries = 3
    while try_count < max_retries:
        now = datetime.now()
        print(f"current time: {now} trying... ({try_count}/{max_retries})")
        try_count += 1
        try:
            mail = connect_to_mail_server(config['imap_server'], config['email_user'], config['email_pass'])
            select_mailbox(mail, "INBOX")
            email_ids = search_emails(mail)

            if not email_ids:
                print(f"current time: {now} No unseen emails found.{email_ids}")
                continue

            matched_emails = fetch_latest_emails(mail, email_ids, target_subjects)
            if not matched_emails:
                continue

            for latest_email_id, msg_data in matched_emails:
                process_email(msg_data, config['save_directory'])
                mail.store(latest_email_id, "+FLAGS", "\\Deleted")
            mail.expunge()
            try_count = max_retries
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
            mail.logout()
            time.sleep(10)

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