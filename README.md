## Pilocator C380 Project
Pi stock notifier, this is a Project that i did with my course group as part of my COMP 380/L Final

Requires Docker Compose

# Building and running your application
### Generate a application password from your google account
This app requires a app password from google you can generate it from [here](https://myaccount.google.com/apppasswords).

it should look something like ``abcd efgh ijkl mnop``, paste this into the `NOTIFICATION_PASSPHRASE` for the environment variable
`NOTIFICATION_EMAIL` would be set to the email of the gmail account.

### Configure the .env file prior to running

``NOTIFICATION_EMAIL``    The email of the gmail account you will be using for sending notifications

``NOTIFICATION_PASSPHRASE``    The passphrase that you get from the link above

``REDIS_HOST``    Does not need changing

``REDIS_PORT``    Does not need changing

``REDIS_USER``    Does not need changing

``REDIS_PASSWORD``    Set to a random password

``REDIS_ARGS:--save 60 1``    Change if redis saves too often for your liking (default 60 seconds)

``FQDN``    If putting behind a domain name you can set the full link here, otherwise emails might link to broken links ex. `FQDN=https://pilo.example.com`

``ENTRY_EXPIRY_TIME``    The expiry time for when entries from rpilocator disappear from the database



## When you're ready, start your application by running:
`docker compose up --build`.

Your application will be available at http://localhost:8080. 

_Please give a minute to allow the table to populate with recent data, might be very barren given low amount of stock updates_

To kill the stack, pressing CTRL + C will stop it
