import json
import jwt

def lambda_handler(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Hello World - Reverification PoC",
        }),
    }