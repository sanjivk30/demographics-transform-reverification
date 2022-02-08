import requests, time, json, jwt, pymysql, datetime

# Gov.UK Notify API URL and extensions
api_base_url = 'https://api.notifications.service.gov.uk'
sms_extension = '/v2/notifications/sms'
email_extension = '/v2/notifications/email'
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
    # MySQL testing - pretty print all rows in table
    cursor = db_connection.cursor()
    cursor.execute("SELECT * FROM Patients")
    rows = cursor.fetchall()
    s = [[str(e) for e in row] for row in rows]
    lens = [max(map(len, col)) for col in zip(*s)]
    fmt = '\t'.join('{{:{}}}'.format(x) for x in lens)
    table = [fmt.format(*row) for row in s]
    print('\n'.join(table))

    # Make MySQL request to fetch all rows from Patients table with required columns
    Patients_cursor = db_connection.cursor()
    Patients_cursor.execute("SELECT patient_ID, first_name, family_name, mobilePhone, emailAddress, flag_ID FROM Patients")
    Patients_rows = Patients_cursor.fetchall()
    # Get column headers for dictionary use
    Patients_columns = [column[0] for column in Patients_cursor.description]

    # Make MySQL request to fetch all rows from Notifications table with required columns
    Notifications_cursor = db_connection.cursor()
    Notifications_cursor.execute("SELECT notification_ID, patient_ID, notification_status, time_stamp FROM Notifications")
    Notifications_rows = Notifications_cursor.fetchall()
    # Get column headers for dictionary use
    Notifications_columns = [column[0] for column in Notifications_cursor.description]
    # Make a list of patient_IDs from the Notifications table that shouldn't be notified
    notified_patient_IDs = []
    for Notifications_row in Notifications_rows:
        # Use column dictionaries as easy identifiers
        row_dict = dict(zip(Notifications_columns, Notifications_row))
        # Make sure the current time is past the grace period for the notification before adding to the list
        notification_timestamp = datetime.datetime.strptime(row_dict["time_stamp"], "%Y-%m-%d %H:%M:%S")
        if datetime.datetime.now() > notification_timestamp + notification_grace_period:
            notified_patient_IDs.append(row_dict["patient_ID"])

    # Send notification one at a time to each patient, using column dictionaries as easy identifiers
    for Patients_row in Patients_rows:
        row_dict = dict(zip(Patients_columns, Patients_row))
        if row_dict["patient_ID"] not in notified_patient_IDs:
            send_notification(row_dict["patient_ID"], row_dict["first_name"], row_dict["family_name"], row_dict["mobilePhone"], row_dict["emailAddress"], row_dict["flag_ID"])


def send_notification(patient_ID, first_name, last_name, mobile_num, email_address, flag_id):
    
    # Select the correct template ID based on the flag ID
    if flag_id in template_IDs:
        template = template_IDs[flag_id]


    # JSON specific headers set-up
    headers = get_json_headers()

    # Personalisation changes variables within created templates
    personalisation = {
        "first_name": first_name,
        "last_name": last_name,
    }

    # JSON body set-up using given information
    body = get_json_body(flag_id, template, personalisation, mobile_num, email_address)

    # Decide on the message type being email or sms, based on the flag ID
    msgType = ""
    if flag_id == 0 or flag_id == 2:
        msgType = sms_extension
    elif flag_id == 1 or flag_id == 3:
        msgType = email_extension

    # Make sure a message type has been decided, then POST the request to the Gov.UK Notify API and print the response
    if len(msgType) > 0:
        send_attempts = 0
        response_code = 500
        while response_code == 500 and send_attempts < max_send_attempts:
            response = requests.post(api_base_url + msgType, data=json.dumps(body), headers=headers)
            print(response.content)
            response_dict = json.loads(response.content)
            response_code = response.status_code
            send_attempts += 1

        # Update Notifications table if request is successful
        if response_code == 201:
            notificationID = response_dict['id']
            notifyStatus = "created"
            notifyTimestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            update_notifications_table(patient_ID, notificationID, notifyStatus, notifyTimestamp)
        else:
            print("LOGGER - LOG response_code and response.content:")
            print(f"status_code: {response_code}\nMessage: {response.content}")

    # If the flag ID is invalid, it needs to be checked from the start to debug, instead of sending an invalid request
    else:
        print("Something went wrong and flag_id is invalid. Please check and try again.")


def get_json_headers():
    payload = {
        'iss': iss,
        'iat': time.time()
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
        'personalisation': personalisation.update({"subject": "NHS Record: Add your mobile number"}),
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
        'personalisation': personalisation.update({"subject": "NHS: Check your mobile number"}),
        # "email_reply_to_id": email_reply_to_id
        }
    return body


def update_notifications_table(patient_ID, notificationID, notifyStatus, notifyTimestamp):
    cursor = db_connection.cursor()
    cursor.execute(f"""INSERT INTO Notifications (notification_ID, patient_ID, notification_status, time_stamp) VALUES
                       ('{notificationID}', {patient_ID}, '{notifyStatus}', '{notifyTimestamp}')""")



# flag_id lookup for possible values. For reference only
"""
flag_id lookup
0: Missing email address (send to mobile)
1: Missing mobile number (send to email)
2: Malformed email address (send to mobile)
3: Malformed mobile number (send to email)
"""

