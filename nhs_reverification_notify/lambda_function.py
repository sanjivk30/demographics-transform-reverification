import requests, time, json, jwt, pymysql, datetime

# Gov.UK Notify API URL and extensions
api_base_url = 'https://api.notifications.service.gov.uk'
sms_extension = '/v2/notifications/sms'
email_extension = '/v2/notifications/email'

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

    # Make MySQL request to fetch all rows with required columns
    cursor = db_connection.cursor()
    cursor.execute("SELECT patient_ID, first_name, family_name, mobilePhone, emailAddress, flag_ID FROM Patients")
    rows = cursor.fetchall()
    # Get column headers for dictionary use
    columns = [column[0] for column in cursor.description]

    # Send notification one at a time to each patient, using column dictionaries as easy identifiers
    for row in rows:
        row_dict = dict(zip(columns, row))
        send_notification(row_dict["patient_ID"], row_dict["first_name"], row_dict["family_name"], row_dict["mobilePhone"], row_dict["emailAddress"], row_dict["flag_ID"])

def send_notification(patient_ID, first_name, last_name, mobile_num, email_address, flag_id):
    
    # Get the template ID from Gov.UK Notify for each flag's unique formatting
    if flag_id == 0:
        template = "bf6b76e1-05a9-40bd-bcb2-b59c0a959c0c"
    elif flag_id == 1:
        template = "bf6b76e1-05a9-40bd-bcb2-b59c0a959c0c"
    elif flag_id == 2:
        template = "bf6b76e1-05a9-40bd-bcb2-b59c0a959c0c"
    elif flag_id == 3:
        template = "bf6b76e1-05a9-40bd-bcb2-b59c0a959c0c"


    # API Key follows the format {key_name}-{iss}-{secret_key}
    key_name = 'reverification_poc'
    iss = '06123232-1c58-42c6-82f8-956834491b85'
    secret_key = 'c3cba708-94ea-46f7-96f6-514f8c571dac'

    # Get the ID for sender's info for when sending a message from Gov.UK Notify settings page
    sms_sender_id = "8e222534-7f05-4972-86e3-17c5d9f894e2"
    email_reply_to_id = "8e222534-7f05-4972-86e3-17c5d9f894e2"

    # JSON specific headers set-up
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

    # Personalisation changes variables within created templates
    personalisation = {
        "first_name": first_name,
        "Family_name": last_name,
    }

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
        "email_reply_to_id": email_reply_to_id
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
        "email_reply_to_id": email_reply_to_id
        }

    # Decide on the message type being email or sms, based on the flag ID
    msgType = ""
    if flag_id == 0 or flag_id == 2:
        msgType = sms_extension
    elif flag_id == 1 or flag_id == 3:
        msgType = email_extension

    # Make sure a message type has been decided, then POST the request to the Gov.UK Notify API and print the response
    if len(msgType) > 0:
        response = requests.post(api_base_url + msgType, data=json.dumps(body), headers=headers)
        print(response.content)
        response_dict = json.loads(response.content)
    # If the flag ID is invalid, it needs to be checked from the start to debug, instead of sending an invalid request
    else:
        print("Something went wrong and flag_id is invalid. Please check and try again.")


    # Update Notifications table
    notificationID = response_dict['id']
    notifyStatus = "created"
    notifyTimestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    update_notifications_table(patient_ID, notificationID, notifyStatus, notifyTimestamp)

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

