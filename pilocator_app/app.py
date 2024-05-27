
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.field import TextField, NumericField, TagField
import smtplib, redis, os, json, requests, re, time, random
from redis.commands.search.query import Query
from redis.commands.json.path import Path
from email.message import EmailMessage
from urllib.parse import parse_qs
from waitress import serve

#Obtain Environment Variables
domainName = os.getenv("FQDN")
hasHttps = os.getenv("HTTPS")
appName = "C380 Pilocator"
abspath = os.path.dirname(__file__)
#Database Variables
dbHost = os.getenv("REDIS_HOST")
dbPort = os.getenv("REDIS_PORT")
dbUser = os.getenv("REDIS_USER")
dbPass = os.getenv("REDIS_PASSWORD")

#Email Variables
emailUser = os.getenv("NOTIFICATION_EMAIL")
emailPass = os.getenv("NOTIFICATION_PASSPHRASE")

#Initialize database connection
db = redis.Redis(
    host= dbHost, port=dbPort,
    username= dbUser, # use your Redis user. More info https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
    password= dbPass, # use your Redis password
    decode_responses=True
)

listingSchema = (
    TextField("$.Item", as_name="name"),
    NumericField("$.instock", as_name="instock"),
    TagField("$.vendor", as_name="vendor"),
    TagField("$.sku", as_name="sku")
)

usrSchema = (
    TagField("$.email", as_name="email"),
    TextField("$.webhook", as_name="webhook"),
    NumericField("$.useEmail", as_name="useemail"),
    TextField("$.verify", as_name="verify"),
    TagField("$.selection", as_name="selection")
)


def RSJsonIndexInit(name, schema, prefixstr):
    rs = db.ft(name)
    #Check if index already exists
    try:
        rs.create_index(
        schema,
        definition=IndexDefinition(prefix=[prefixstr], index_type=IndexType.JSON)
        )
    except:
        rs.dropindex()
        rs.create_index(
        schema,
        definition=IndexDefinition(prefix=[prefixstr], index_type=IndexType.JSON)
        )
    
    return rs

#Redis Initialization
rsuser = RSJsonIndexInit("users", usrSchema, "users:")
rsstock = RSJsonIndexInit("stock", listingSchema, "stock:")

def checkAndEscape(email):
    if not (re.fullmatch(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', email)):
        return ""
    #Escape special characters or else redis search will error out
    escaped = email.translate(str.maketrans({
        "-":  r"\-",
        "]":  r"\]",
        "\\": r"\\",
        "^":  r"\^",
        "$":  r"\$",
        "*":  r"\*",
        ".":  r"\.",
        "@":  r"\@",
        "+":  r"\+",
        "_":  r"\_",
        }))
    return escaped

def searchByEmail(email):
    newEmail = checkAndEscape(email)
    try:
        print("Searching for: " + newEmail)
        res = rsuser.search(Query(r"@email:{" + newEmail + r"}")).docs
    except:
        print("Bad email formatted (" + email + ")")
        return ""
    if len(res) > 0:
        print(res[0].id)
        return res[0].id
    else:
        return None
    
def generate_code(length=12):
    code = ''.join(random.choices('0123456789', k=length))
    return code
def adduser(email, selection, choice, webhook= ""):
    newEmail = checkAndEscape(email)
    res = None
    id = None
    if newEmail == "":
        print("Invalid Email")
        return
    #Checking if email exists in database, if it does then just update the entry instead of creating a new one
    try:
        print("Searching for: " + newEmail)
        res = rsuser.search(Query(r"@email:{" + newEmail + r"}")).docs
        print(res)
    except:
        print("Bad email formatted (" + email + ")")
        return
    
    if len(res) > 0:
        print("Found an existing entry")
        id = res[0].id
    else:
        print("Not found, creating...")
        id = "users:" + str(int(time.time())) + email
        
    print(db.json().set(id, Path.root_path(), {
        "email": email,
        "webhook": webhook,
        "useEmail": choice,
        "selection": selection
    } ))
    
    print("User " + id + " Updated")

def getEntry(guid):
    try:
        return db.hgetall(guid)
    except:
        return None
    return None

def notify(msg):
    model = getEntry(msg["data"])
    userlist = rsuser.search("@selection:{" + model["sku"] + "}").docs
    for x in userlist:
        info = json.loads(x.json)
        if info["useEmail"] == 1:
            print("Notifying " + info["email"] + " via email " + model["link"])
            subject = appName + ": Stock Update Notification"
            bodymessage = model["sku"] + " is now in stock at " + model["vendor"] + " with at least " + model["instock"] + " available!\n" 
            bodymessage += model["link"]
            bodymessage += "\n"
            bodymessage += "You can unsusbscribe or update your notification preferences at https://pilocator.mike.ong/subscribe/"
            sendEmail(subject, bodymessage,info["email"])
        else:
            print("Notifying " + info["email"] + " via webhook "+ model["link"])
            content = {
            "content": "",
            "embeds": [
                {
                "color": 5814783,
                "fields": [
                    {
                    "name": appName + ": Stock Update Notification",
                    "value": model["sku"] + " is now in stock at " + model["vendor"] + " with at least " + model["instock"] + " available!\n" + model["link"]
                    }],
                "footer": {
                    "text": "You can unsusbscribe or update your notification preferences at https://pilocator.mike.ong/subscribe/"
                }
                }
            ],
            "attachments": []
            }
            sendWebhook(info["webhook"], json.dumps(content))

#Send Email
def sendEmail(subject,body,to):
    print("Sending email to " + to)
    if emailUser == "" or emailPass == "":
        print("Email account not configured, cancelling send")
        return
    msg = EmailMessage()
    msg.set_content(body)
    msg['from'] = emailUser
    msg['subject'] = subject
    msg['to'] = to
    
    #Authentication
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(emailUser,emailPass)
    server.send_message(msg)
    
    server.quit()
def sendWebhook(hook, content):
    req = requests.post(hook, content, headers={'Content-type' : 'application/json' })
    print(req.status_code)
    return

#Redis Notification Handler
pubsub = db.pubsub()
subscribe_key = 'entries'
pubsub.psubscribe(**{subscribe_key: notify})

pubsub.run_in_thread(sleep_time=.01)
#Webpages
def homepage(environ, start_response):
    headers = [('Content-type', 'text/html')]
    with open(os.path.join(abspath, 'site/index.html'), 'rb') as file:
        content = file.read()
    start_response('200 OK', headers)
    return [content]

def subscribe(environ, start_response):
    headers = [('Content-type', 'text/html')]
    with open(os.path.join(abspath,'site/signin.html'), 'rb') as file:
        content = file.read()
    start_response('200 OK', headers)
    return [content]
def about(environ, start_response):
    headers = [('Content-type', 'text/html')]
    with open(os.path.join(abspath,'site/about.html'), 'rb') as file:
        content = file.read()
    start_response('200 OK', headers)
    return [content]

#Backend
def signup(environ, start_response):
    if environ['REQUEST_METHOD'] != 'POST':
        # If the request method is not POST, return a 405 Method Not Allowed response
        response_body = json.dumps({'error': 'Method Not Allowed'})
        status = '405 Method Not Allowed'
        response_headers = [('Content-type', 'application/json')]
        start_response(status, response_headers)
        return [response_body.encode('utf-8')]
    content_length = int(environ.get('CONTENT_LENGTH', 0))
    if not content_length:
        # If the request does not contain JSON data, return an error response
        response_body = json.dumps({'error': 'Request must contain JSON data'})
        status = '400 Bad Request'
        response_headers = [('Content-type', 'application/json')]
        start_response(status, response_headers)
        return [response_body.encode('utf-8')]
    
    request_body = environ['wsgi.input'].read(content_length)
    data = json.loads(request_body.decode('utf-8'))
    
    # Process the JSON data
    email = data.get('emailaddress')
    webhook = data.get('webhookaddress')
    useEmail = data.get('choice')
    selection = data.get('selection[]') 
    
    # Check if the variables are not blank
    if not (email and useEmail and selection) and (useEmail == "email" or useEmail == "webhook"):
        response_body = json.dumps({'error': 'Bad JSON info'})
        status = '400 Bad Request'
        response_headers = [('Content-type', 'application/json')]
        start_response(status, response_headers)
        return [response_body.encode('utf-8')]
    
    useEmail = 1 if useEmail == "email" else 0
    if useEmail == 0 and (webhook == None or webhook == ""):
        response_body = json.dumps({'error': 'Bad JSON info'})
        status = '400 Bad Request'
        response_headers = [('Content-type', 'application/json')]
        start_response(status, response_headers)
        return [response_body.encode('utf-8')]
    token = str(generate_code())
    pending = {
        "email": email,
        "webhook": webhook,
        "useEmail": useEmail,
        "selection": selection
    }
    bodymessage = ""

    if searchByEmail(email) is None:
        print(email + " is subscribing")
        bodymessage += "You are signing up for notifications for when raspberry pis are in stock\n"
        bodymessage += " ".join(str(x) for x in selection)
        bodymessage += "\n"
        bodymessage += domainName + "/confirm" + "?user="+email + "&token=" + token
        bodymessage += "\nOpen this link to sign up, else just ignore it"
        bodymessage += "\nThis link will expire a day from now."
    else:
        print(email + " is updating their preferences")
        bodymessage += "You tried updating your preferences for when raspberry pis are in stock\n"
        bodymessage += " ".join(str(x) for x in selection)
        bodymessage += "\n"
        bodymessage += domainName + "/confirm" + "?user="+email + "&token=" + token
        bodymessage += "\nOpen this link to update your preferences, else just ignore it"
        bodymessage += "\nThis link will expire a day from now."


    db.set("pending:"+token, json.dumps(pending))
    db.expire("pending:"+token, 86400) #Expire after 1 day
    print(appName +" : Notifications" + " " + bodymessage + " " + email)
    if (sendEmail(appName +" : Notifier", bodymessage, email)):
        print("Successfully sent email")
    # Return a JSON response indicating success
    response_body = json.dumps({'message': 'JSON data received successfully'})
    status = '200 OK'
    response_headers = [('Content-type', 'application/json')]
    start_response(status, response_headers)
    return [response_body.encode('utf-8')]

def unsub(environ, start_response):
    headers = [('Content-type', 'text/plain')]
    query_string = environ.get('QUERY_STRING', '')
    query_params = parse_qs(query_string)
    user = query_params.get('email', [''])[0]

    try:
        uid = searchByEmail(user)
        db.json().delete(uid)
        print("deleted " + uid)
    except:
        print("Failed to delete user with the email: " + user)
    start_response('200 OK', headers)
    body = "Unsubscribed " + user + " if account existed"
    return [bytes(body, 'utf-8')]

def confirm(environ, start_response):
    headers = [('Content-type', 'text/plain')]
    query_string = environ.get('QUERY_STRING', '')

    # Parse the query string into a dictionary
    query_params = parse_qs(query_string)
    user = query_params.get('user', [''])[0]
    token = query_params.get('token', [''])[0]
    if user and token:
        res = db.get("pending:"+token)
        if res != None:
            update = json.loads(res)
            if update["email"] == user:
                adduser(update["email"], update["selection"], update["useEmail"], update["webhook"])
                db.delete("pending:"+token)
                start_response('200 OK', headers)     
                return [b'Confirmed']
    status = '400 Bad Request'
    response_headers = [('Content-type', 'text/plain')]
    start_response(status, response_headers)
    return [b'No.']

def getData(environ, start_response):   
    print("A visitor.")
    data = list()
    vendcount = [0,0,0,0,0]
    try:
        res = db.scan(match="entries:*", count=10)[1]
        for x in res:
            entry = db.hgetall(x)
            ven = entry["vendor"]
            if ven == "adafruit":
                vendcount[0] += 1
            if ven == "chicagodist":
                vendcount[1] += 1
            if ven == "digikeyus":
                vendcount[2] += 1
            if ven == "newark":
                vendcount[3] += 1
            if ven == "pishopus":
                vendcount[4] += 1
            data.append(entry)
    except:
        print("couldnt get the table, somethings wrong here")
        status = '500'
        response_headers = [('Content-type', 'application/json')]
        start_response(status, response_headers)
        return ["{}".encode('utf-8')]
    
    body = {
        "summary": vendcount,
        "data": data
    }
    status = '200 OK'
    response_headers = [('Content-type', 'application/json')]
    start_response(status, response_headers)
    return [json.dumps(body).encode('utf-8')]

def pilocator(environ, start_response):
    path = environ.get('PATH_INFO')
    # Define your routes
    if path == '/':
        return homepage(environ, start_response)
    elif path == '/subscribe':
        return subscribe(environ, start_response)
    elif path == '/about':
        return about(environ, start_response)
    elif path == '/signup':
        return signup(environ, start_response)
    elif path == '/unsubscribe':
        return unsub(environ, start_response)
    elif path == '/getData':
        return getData(environ, start_response)
    elif path == '/confirm':
        return confirm(environ, start_response)
    else:
        # Return a 404 Not Found response for unknown routes
        start_response('404 Not Found', [('Content-type', 'text/plain')])
        return [b'Not Found']

#Start server
if __name__ == '__main__':
    serve(pilocator, host='0.0.0.0', port=8080)
