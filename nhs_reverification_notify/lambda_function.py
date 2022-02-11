from re import I
import requests, time, json, jwt, pymysql, datetime

# Gov.UK Notify API URL
api_base_url = 'https://api.notifications.service.gov.uk'
# API Key follows the format {key_name}-{iss}-{secret_key}
# key_name = 'nhs_reverification_service'  # Not needed
iss = '7ebefa63-8038-44d5-aca9-650a1e803f8f'
secret_key = '6929b4db-906b-4dd5-bfcf-a2ddb7d36357'
# Template ID from Gov.UK Notify for each flag's unique formatting
template_IDs = {
    0: "3fedbadf-b419-4834-bfbc-2e9082477a99",
    1: "de3f9885-af6e-4392-ae60-f543806e6d85",
    2: "20bea17e-562c-4e53-91da-62c99530ae68",
    3: "a24c58cc-f31c-448a-aee9-01ded9e0d552"
}
# Get the ID for sender's info for when sending a message from Gov.UK Notify settings page
sms_sender_id = "9792f0d6-6cd5-4c3b-b1c1-2c75c7c8e1c2"
# email_reply_to_id = "8e222534-7f05-4972-86e3-17c5d9f894e2"  # Not including reply emails

# Maximum number of notification sending attempts in case of failure
max_send_attempts = 3
# Set the minimum grace period wait time between sent notifications to the same patient
notification_grace_period = datetime.timedelta(days=7)

# Database config values
db_endpoint = "cohort-test.c8qpdaxefdlf.us-east-1.rds.amazonaws.com"
db_username = "admin"
db_password = "testpassword"
db_name = "cohort_db"

# Database connection 
db_connection = pymysql.connect(host=db_endpoint, user=db_username, password=db_password, database=db_name)

def lambda_handler(event, context):
    # Make MySQL request to fetch all rows from Patients table with required columns
    patients_columns, patients_rows = get_all_rows("Patients", "patient_ID", "first_name", "family_name", "mobilePhone", "emailAddress", "flag_ID")

    # Make MySQL request to fetch all rows from Notifications table with required columns
    notifications_columns, notifications_rows = get_all_rows("Notifications", "notification_ID", "patient_ID", "notification_status", "time_stamp")

    # Make a list of patient_IDs from the Notifications table that shouldn't be notified
    exempt_patient_IDs = get_exempt_patient_IDs(notifications_columns, notifications_rows)

    # Send notification one at a time to each patient, using column dictionaries as easy identifiers
    for patients_row in patients_rows:
        patient_dict = dict(zip(patients_columns, patients_row))
        if patient_dict["patient_ID"] not in exempt_patient_IDs:
            send_notification(patient_dict["patient_ID"], patient_dict["first_name"], patient_dict["family_name"],
            patient_dict["mobilePhone"], patient_dict["emailAddress"], patient_dict["flag_ID"])


def get_all_rows(table_name, *args):
    cursor = db_connection.cursor()
    cursor.execute(f"SELECT {', '.join(args)} FROM {table_name}")
    rows = cursor.fetchall()
    # Get column headers for dictionary use
    columns = [column[0] for column in cursor.description]

    return columns, rows


def get_exempt_patient_IDs(notifications_columns, notifications_rows):
    exempt_patient_IDs = []
    for notifications_row in notifications_rows:
        # Use column dictionaries as easy identifiers
        patient_row_dict = dict(zip(notifications_columns, notifications_row))
        # Make sure the current time is past the grace period for the notification before adding to the list
        notification_timestamp = datetime.datetime.strptime(patient_row_dict["time_stamp"], "%Y-%m-%d %H:%M:%S")
        datetime_now = datetime.datetime.now()
        grace_end_datetime = notification_timestamp + notification_grace_period
        if datetime_now < grace_end_datetime:  # ----------------------------------Requires unit testing--------------------------------------------
            print(f"Patient {patient_row_dict['patient_ID']} is exempt. Notification sent: {patient_row_dict['time_stamp']}")
            exempt_patient_IDs.append(patient_row_dict["patient_ID"])
    
    return exempt_patient_IDs


def send_notification(patient_ID, first_name, last_name, mobile_num, email_address, flag_id):
    
    # Select the correct template ID based on the flag ID
    if flag_id in template_IDs:
        template = template_IDs[flag_id]


    # JSON specific headers set-up
    headers = get_json_headers(iss, time.time(), secret_key)

    # Personalisation changes variables within created templates
    personalisation = {
        "first_name": first_name,
        "last_name": last_name,
    }

    # JSON body set-up using given information
    body = get_json_body(flag_id, template, personalisation, mobile_num, email_address)

    # Decide on the message type being email or sms, based on the flag ID
    msg_ext = get_message_extension(flag_id)

    # Make sure a message type has been decided, then POST the request to the Gov.UK Notify API and print the response
    if msg_ext is not None and len(msg_ext) > 0:
        notify_api = api_base_url + msg_ext
        data = json.dumps(body)
        notificationID = get_notification_id(notify_api, data, headers, 0, max_send_attempts)

        # Update Notifications table if request is successful
        if notificationID != None:
            notify_timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_notifications_table(patient_ID, notificationID, "created", notify_timestamp)

    # If the flag ID is invalid, it needs to be checked from the start to debug, instead of sending an invalid request
    else:
        print("LOGGER - LOG invalid flag_id. Internal error.")


def get_notification_id(notify_api, data, headers, send_attempts, max_attempts):
    if send_attempts > max_attempts:
        print(f"Max attempts reached for payload: {data}")
        return None
    response = requests.post(notify_api, data=data, headers=headers)
    print(f"API Response: {response.content}")
    if response.status_code == 201:
        return json.loads(response.content).get('id', None)
    print(f"Error for payload: '{data}'. Response code: '{response.status_code}'")
    return get_notification_id(notify_api, data, headers, send_attempts + 1, max_attempts)


def get_message_extension(flag_id):
    if flag_id == 0 or flag_id == 2:
        return '/v2/notifications/sms'
    elif flag_id == 1 or flag_id == 3:
        return '/v2/notifications/email'
    else:
        return None


def get_json_headers(iss, time_point, secret_key):
    payload = {
        'iss': iss,
        'iat': time_point
    }
    # JSON Web Token Encoding
    auth = jwt.encode(payload, secret_key, algorithm='HS256')
    headers = {
        'typ': 'JWT',
        'alg': 'HS256',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + auth
    }
    return headers


def get_json_body(flag_id, template, personalisation, mobile_num, email_address):
    # Use a specific body of information for each flag ID
    if flag_id == 0:
        body = {
        'phone_number': mobile_num,
        'template_id': template,
        'personalisation': personalisation,
        "sms_sender_id": sms_sender_id
        }
    elif flag_id == 1:
        body = {
        'email_address': email_address,
        'template_id': template,
        'personalisation': personalisation,
        # "email_reply_to_id": email_reply_to_id
        }
    elif flag_id == 2:
        body = {
        'phone_number': mobile_num,
        'template_id': template,
        'personalisation': personalisation,
        "sms_sender_id": sms_sender_id
        }
    elif flag_id == 3:
        body = {
        'email_address': email_address,
        'template_id': template,
        'personalisation': personalisation,
        # "email_reply_to_id": email_reply_to_id
        }
    return body


def update_notifications_table(patient_ID, notificationID, notify_status, notify_timestamp):
    cursor = db_connection.cursor()
    insert_sql = "INSERT INTO Notifications (notification_ID, patient_ID, notification_status, time_stamp) VALUES (%s, %s, %s, %s)"
    insert_values = (notificationID, patient_ID, notify_status, notify_timestamp)
    cursor.execute(insert_sql, insert_values)
    db_connection.commit()



# flag_id lookup for possible values. For reference only
"""
flag_id lookup
0: Missing email address (send to mobile)
1: Missing mobile number (send to email)
2: Malformed email address (send to mobile)
3: Malformed mobile number (send to email)
"""

