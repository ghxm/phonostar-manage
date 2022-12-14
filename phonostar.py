import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
import re
import atexit
import configparser
from tqdm import tqdm
import requests
import os
import time
import re

def exit_handler():
    try:
        # close the browser
        driver.close()
    except:
        pass

atexit.register(exit_handler)

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("command",
        help="the command to be executed",
        choices=["list", "download", "delete"],
        nargs='?',
        default="list"
    )
parser.add_argument('-r', '--regex', type=str, required=False, help='Specify a regex for recordings to match')
parser.add_argument('-d', '--delete-after-download', action="store_true", required=False, help='Delete recordings after successful download')
parser.add_argument('-u', '--user', type=str, default="", required=False, help='Username')
parser.add_argument('-p', '--password', type=str, default="", required=False, help='Password')
parser.add_argument('-c', '--config', type=str, default='', required=False, help='path to config.ini file')
parser.add_argument('--geckodriver-path', type=str, default='geckodriver', required=False, help='path to geckodriver executable')
parser.add_argument('--firefox-path', type=str, default='firefox', required=False, help='path to firefox executable')
parser.add_argument('--debug', action='store_true', default = False, required=False, help='Debug mode')
parser.add_argument('--dir', type=str, default=".", required=False, help='Download dir')

args = parser.parse_args()

if args.command == 'delete' and args.regex is None:
    print("WARNING: This will delete all recordings. Use -r to specify a regex to match recordings to delete.")
    print("Press enter to continue or ctrl+c to cancel.")
    input()

if args.config != '':
    config = configparser.ConfigParser()
    config.read(args.config)
    args.user = config.get('auth', 'user')
    args.password = config.get('auth', 'password')
    args.dir = config.get('download', 'dir')


ff_ops = Options()

ff_ops.binary_location = args.firefox_path

ff_ops.set_preference("browser.download.manager.showWhenStarting", False)
ff_ops.set_preference("browser.download.folderList", 2)
ff_ops.set_preference("browser.download.useDownloadDir", True)

if not args.debug:
    ff_ops.headless = True

if args.dir != '':
    ff_ops.set_preference("browser.download.dir", args.dir)

ff_service = Service(args.geckodriver_path)

# create a new Firefox session
driver = webdriver.Firefox(options=ff_ops, service=ff_service)
driver.implicitly_wait(10)

# navigate to the application home page
driver.get("https://www.phonostar.de/radio/radioaufnehmen/radiocloud/login")
assert "phonostar" in driver.title

def delete_recording(recording):

    print ("Deleting recording: " + recording.get('title', '') + " " + recording.get('date', ''))

    delete_successful = False

    i = 1

    while not delete_successful and i < 3:

        i = i + 1

        try:
            # click on the recording delte button
            recording.get('delete_button').click()

            # wait for the delete confirmation dialog to appear
            WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CLASS_NAME, "ui-dialog")))

            # find button to confirm deletion
            delete_button = driver.find_element(By.XPATH, "//button[contains(text(), 'OK')]")

            # click on the delete button
            delete_button.click()

            delete_successful = True
        except:
            accept_cookie_notice()
            delete_successful = False




def download_recording(recording, trials = 2):
    
    print('Downloading ' + rec['title'] + '...')

    # click on the recording download button
    download_link = recording.get('download_link')

    filename = recording.get('title', '').replace(' ', '_').replace('|', '') + '_' + recording.get('date', '').replace(' ', '_').replace('|', '') + '.mp3'

    # check if dir exists, if not, create
    if not os.path.exists(args.dir):
        os.makedirs(args.dir)

    filepath = os.path.join(args.dir, filename)

    # copy driver cookies
    driver_cookies = driver.get_cookies()
    cookies_copy = {}
    for driver_cookie in driver_cookies:
        cookies_copy[driver_cookie["name"]] = driver_cookie["value"]

    download_successful = False

    n = 0

    while n <= trials and not download_successful:

        try:
            # download the file

            response = requests.get(download_link, stream=True, cookies=cookies_copy)
            total_size_in_bytes = int(response.headers.get('content-length', 0))
            block_size = 1024  # 1 Kibibyte
            progress_bar = tqdm(total=total_size_in_bytes, unit='iB', unit_scale=True)
            with open(filepath, 'wb') as file:
                for data in response.iter_content(block_size):
                    progress_bar.update(len(data))
                    file.write(data)
            progress_bar.close()
            if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
                print("ERROR, something went wrong")
                raise Exception()
            download_successful = True
        except:
            n = n + 1

    if not download_successful:
        raise Exception()

def accept_cookie_notice():
    try:
        # check for cookie window
        WebDriverWait(driver, 5).until(
            EC.frame_to_be_available_and_switch_to_it((By.XPATH, "//iframe[contains(@id,'sp_message')]")))

        driver.find_element(By.TAG_NAME, 'button').click()

        # switch back to main window
        driver.switch_to.default_content()

    except:
        pass


def parse_recording(recording):
    title = recording.find_element(By.CLASS_NAME, "li-heading-main").text
    date = recording.find_element(By.CLASS_NAME, "description").text
    duration = recording.find_element(By.CLASS_NAME, "recording-duration-display").text
    try:
        download_link = recording.find_element(By.CLASS_NAME, "recording-actions").find_element(By.TAG_NAME,
                                                                                                "a").get_attribute(
            "href")
    except:
        download_link = None
    delete_button = recording.find_element(By.TAG_NAME, "form").find_element(By.NAME, "button")

    return({
        "title": title,
        "date": date,
        "duration": duration,
        "download_link": download_link,
        "delete_button": delete_button,
        "series_episode": False
    })


def parse_compact_recording(recording):

    spans = recording.find_elements(By.XPATH, "./span")

    if len(spans) == 4:
        title = spans[1].text
        date = re.sub('\s*\|.*', '', spans[2].text)

        try:
            download_link = spans[3].find_element(By.TAG_NAME, "a").get_attribute("href")
        except:
            download_link = None

        delete_button = spans[3].find_element(By.TAG_NAME, "form").find_element(By.NAME, "button")

    else:

        # try to guess the span information

        for span in spans:
            if span.text == '':
                continue

            if re.search('^\d{2}\.\d{2}\.\d{4}$', span.text) is not None:
                date = span.text
                continue

            if len(span.find_elements(By.TAG_NAME, "a"))> 0:
                try:
                    download_link = span.find_element(By.TAG_NAME, "a").get_attribute("href")
                except:
                    download_link = None

                delete_button = span.find_element(By.TAG_NAME, "form").find_element(By.NAME, "button")
                continue

            title = span.text

    return({
        "title": title,
        "date": date,
        "download_link": download_link,
        "delete_button": delete_button,
        "series_episode": True
    })









login_successful = False

login_trials = 0

while not login_successful and login_trials <= 3:

    try:
        accept_cookie_notice()

        login_trials = login_trials + 1

        # get the username textbox
        login_field = driver.find_element(By.ID, "user_email")
        login_field.clear()

        # enter username
        if args.user == "":
            login_field.send_keys(input("Username: "))
        else:
            login_field.send_keys(args.user)

        # get the password textbox
        password_field = driver.find_element(By.ID, "user_password")
        password_field.clear()

        # enter password
        if args.password == "":
            password_field.send_keys(input("Password: "))
        else:
            password_field.send_keys(args.password)

        # login
        password_field.send_keys(Keys.RETURN)

        # check if login was successful
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CLASS_NAME, "dashboard")))
            login_successful = True
            print('Login successful.')
        except:
            print("Login failed. Please try again.")
            args.user = ""
            args.password = ""

    except:
        if login_trials <= 3:
            print('Login failed. Trying again...')
        else:
            print('Login failed in ' + str(login_trials) + ' trials. Exiting.')
            exit()

recordings_found_succesful = False

recordings_found_trials = 0

while not recordings_found_succesful and recordings_found_trials <= 3:

    try:

        recordings_found_trials = recordings_found_trials + 1

        # navigate to the recordings page
        driver.get("https://www.phonostar.de/radio/radioaufnehmen/radiocloud/aufnahmen")

        recordings_table = None
        recordings_table_trials = 0

        while recordings_table is None and recordings_table_trials <= 3:

            recordings_table_trials = recordings_table_trials + 1

            time.sleep(1)

            accept_cookie_notice()
            # get the recordings table
            recordings_table = driver.find_element(By.XPATH, "//div[contains(concat(' ', @class, ' '), ' radiocloud-recordings ')]")


        # get the recordings
        recordings = recordings_table.find_elements(By.TAG_NAME, "li")

        recs = []

        # iterate over the recordings
        for recording in recordings:

            # check for bad size
            if recording.size.get('height') == 0 or recording.size.get('width') == 0:
                continue


            # check for series container
            if len(recording.find_elements(By.XPATH, "./ul")) > 0:
                continue

            # check for compact recording
            if len(recording.find_elements(By.XPATH, "./span[contains(@class, 'compact-radiocloud-recording')]")) > 0:
                try:
                    recs.append(parse_compact_recording(recording))
                except:
                    continue
            else:
                try:
                    recs.append(parse_recording(recording))
                except:
                    continue


        recordings_found_succesful = True

    except:
        if recordings_found_trials <= 3:
            print('Recordings page not found. Trying again...')
        else:
            print('Recordings page not found in ' + str(recordings_found_trials) + ' trials. Exiting.')
            exit()

if args.regex:
    recs = list(filter(lambda x: re.search(args.regex, x.get('title')), recs))

if len(recs) == 0:
    print("No recordings found.")
    exit()

if args.command == 'list':
    print('Found {} recordings:'.format(len(recs)))
    for rec in recs:
        print(rec)
        print('\r')

if args.command == 'download':
    print('Downloading {} recordings:'.format(len(recs)))
    for rec in recs:
        try:
            download_recording(rec)
            if args.delete_after_download:
                delete_recording(rec)
        except:
            print('Error downloading ' + rec['title'])
        print('\r')

if args.command == 'delete':
    print('Deleting {} recordings:'.format(len(recs)))
    for rec in recs:
        try:
            delete_recording(rec)
        except:
            print('Error deleting ' + rec['title'])
            print('\r')

exit()