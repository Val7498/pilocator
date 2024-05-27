import requests
import bs4 as bs
import re
import redis
import os

#Obtain Environment Variables
dbHost = os.getenv("REDIS_HOST")
dbPort = os.getenv("REDIS_PORT")
dbUser = os.getenv("REDIS_USER")
dbPass = os.getenv("REDIS_PASSWORD")
expiry = os.getenv("EXPIRY_TIME")
vendorlist = ["adafruit", "chicagodist", "digikeyus", "newark", "pishopus"]
skulist = [ "PI4", "PI5", "PIZERO", "PIZERO2"]

vendors = {
    "adafruit": {
        "PI4": "https://www.adafruit.com/product/4292",
        "PI5": "https://www.adafruit.com/product/5812",
        "PIZERO": "https://www.adafruit.com/product/3400",
        "PIZERO2": "https://www.adafruit.com/product/5291"
    },
    "chicagodist": {
        "PI4": "https://chicagodist.com/collections/raspberry-pi",
        "PI5": "https://chicagodist.com/collections/raspberry-pi-5/products/raspberry-pi-5-8gb",
        "PIZERO": "https://chicagodist.com/collections/raspberry-pi",
        "PIZERO2": "https://chicagodist.com/products/raspberry-pi-zero-2"
    },
    "digikeyus": {
        "PI4": "https://www.digikey.com/en/product-highlight/r/raspberry-pi/raspberry-pi-4-model-b",
        "PI5": "https://www.digikey.com/en/product-highlight/r/raspberry-pi/raspberry-pi-5",
        "PIZERO": "https://www.digikey.com/en/supplier-centers/raspberry-pi",
        "PIZERO2": "https://www.digikey.com/en/product-highlight/r/raspberry-pi/raspberry-pi-zero-2-w"
    },
    "newark": {
        "PI4": "https://www.newark.com/raspberry-pi/rpi4-modbp-4gb/soc-type-broadcom-bcm2711/dp/02AH3164",
        "PI5": "https://www.newark.com/buy-raspberry-pi",
        "PIZERO": "https://www.newark.com/c/raspberry-pi",
        "PIZERO2": "https://www.newark.com/raspberry-pi/rpi-zero-w-v2/raspberry-pi-kit-64bit-arm-cortex/dp/71AJ9644"
    },
    "pishopus": {
        "PI4": "https://www.pishop.us/product/raspberry-pi-4-model-b-4gb/",
        "PI5": "https://www.pishop.us/product/raspberry-pi-5-8gb/",
        "PIZERO": "https://www.pishop.us/product/raspberry-pi-zero/",
        "PIZERO2": "https://www.pishop.us/product/raspberry-pi-zero-2-w/"
    },
    # Add more vendors and SKUs as needed
}


db = redis.Redis(
    host= dbHost, port=dbPort,
    username= dbUser, # use your Redis user. More info https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
    password= dbPass, # use your Redis password
    decode_responses=True
)

def scrape():
    #Get feed from site
    page = requests.get('https://rpilocator.com/feed/?country=US&cat=PI4,PI5,PIZERO,PIZERO2')
    soup = bs.BeautifulSoup(page.text, 'xml')
    entries = soup.findAll('item')
    p = db.pipeline()
    #Iterate through all entries
    for item in entries:
        #Check in database if it exists already
        guid = item.find("guid").text.strip()
        if db.hgetall("entries:" + guid) != {}:
            continue
        vendor = None
        sku = None
        product_link = " "
        instock = -1
        #Get sku and vendor
        for cat in item.findAll('category'):
            if cat.text in vendorlist:
                vendor = cat.text
            if cat.text in skulist:
                sku = cat.text    
        #Attempt to get stock amount
        match = re.search(r'(\d+) units in stock.', item.find("description").text)
        if match:
            instock = int(match.group(1))
        if vendor and sku:
            if sku in vendors[vendor]:
                product_link = vendors[vendor][sku]
            else:
                product_link = "https://" + vendor.replace(" ", "") + ".com"  # Use vendor's main page as fallback
    
        p.hset("entries:" + guid, "vendor", vendor)
        p.hset("entries:" + guid, "sku", sku)
        p.hset("entries:" + guid, "instock", instock)           
        p.hset("entries:" + guid, "link", product_link) # Parser WIP
        p.expire("entries:" + guid, expiry) #Set Expiry time to avoid clogging the database with old entries
        p.publish("entries", "entries:" + guid)
        print('{} of {} at {}'.format(instock, sku,vendor)) #Log in console
    p.execute()

if __name__ == "__main__":
    scrape()