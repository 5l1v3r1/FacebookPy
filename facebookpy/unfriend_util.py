from datetime import datetime
import sqlite3
# import time
from math import ceil
import random

from socialcommons.time_util import sleep
from socialcommons.util import update_activity
from socialcommons.util import click_element
from socialcommons.util import emergency_exit
from socialcommons.util import load_user_id
from socialcommons.util import explicit_wait
from socialcommons.util import find_user_id
from socialcommons.util import get_username_from_id
from socialcommons.util import is_page_available
from socialcommons.util import reload_webpage
from socialcommons.util import web_address_navigator
from socialcommons.util import click_visibly
from socialcommons.print_log_writer import log_friended_pool
from socialcommons.database_engine import get_database
from socialcommons.quota_supervisor import quota_supervisor
from .settings import Settings
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import ElementNotVisibleException
from selenium.webdriver.common.action_chains import ActionChains
import pyautogui

HOME = "/Users/ishandutta2007"
CWD = HOME + "/Documents/Projects/FacebookPy"

def verify_username_by_id(browser, username, person, person_id, logger,
                          logfolder):
    """ Check if the given user has changed username after the time of
    followed """
    # try to find the user by ID
    if person_id is None:
        person_id = load_user_id(username, person, logger, logfolder)

    if person_id and person_id not in [None, "unknown", "undefined"]:
        # get the [new] username of the user from the stored user ID
        person_new = get_username_from_id(browser, "https://www.facebook.com", person_id, logger)
        if person_new:
            if person_new != person:
                logger.info(
                    "User '{}' has changed username and now is called '{}' :S"
                    .format(person, person_new))
            return person_new

        else:
            logger.info(
                "The user with the ID of '{}' is unreachable".format(person))

    else:
        logger.info(
            "The user ID of '{}' doesn't exist in local records".format(
                person))

    return None

def get_friending_status(browser, track, username, person, person_id, logger,
                         logfolder):
    """ Verify if you are friending the user in the loaded page """
    if track == "profile":
        ig_homepage = "https://www.facebook.com/"
        web_address_navigator( browser, ig_homepage + person, Settings)

    friend_button_XP = ("//div[@id='fbTimelineHeadline']/div/div/div/div/button[@type='button'][text()='Add Friend']")
    failure_msg = "--> Unable to detect the friending status of '{}'!"
    user_inaccessible_msg = (
        "Couldn't access the profile page of '{}'!\t~might have changed the"
        " username".format(person))

    # check if the page is available
    valid_page = is_page_available(browser, logger, Settings)
    if not valid_page:
        logger.warning(user_inaccessible_msg)
        person_new = verify_username_by_id(browser,
                                           username,
                                           person,
                                           None,
                                           logger,
                                           logfolder)
        if person_new:
            web_address_navigator( browser, ig_homepage + person_new, Settings)
            valid_page = is_page_available(browser, logger, Settings)
            if not valid_page:
                logger.error(failure_msg.format(person_new.encode("utf-8")))
                return "UNAVAILABLE", None

        else:
            logger.error(failure_msg.format(person.encode("utf-8")))
            return "UNAVAILABLE", None

    # wait until the friend button is located and visible, then get it
    friend_button = explicit_wait(browser, "VOEL", [friend_button_XP, "XPath"],
                                  logger, 7, False)
    if not friend_button:
        browser.execute_script("location.reload()")
        update_activity(Settings)

        friend_button = explicit_wait(browser, "VOEL",
                                      [friend_button_XP, "XPath"], logger, 14,
                                      False)
        if not friend_button:
            # cannot find the any of the expected buttons
            logger.error(failure_msg.format(person.encode("utf-8")))
            return None, None

    # get friend status
    friending_status = friend_button.text

    return friending_status, friend_button


def friend_user(browser, track, login, userid_to_friend, times, blacklist,
                logger, logfolder):
    """ Friend a user either from the profile page or post page or dialog
    box """
    # list of available tracks to friend in: ["profile", "post" "dialog"]

    # check action availability
    if quota_supervisor(Settings, "friends") == "jump":
        return False, "jumped"

    # check URL of the webpage, if it already is user's profile
    # page, then do not navigate to it again
    if friend_restriction("read", userid_to_friend, 1, logger):
        logger.info("Already connected {} or more times".format(times))
        return False, "already friended"

    user_link = "https://www.facebook.com/{}/".format(userid_to_friend)
    web_address_navigator( browser, user_link, Settings)

    # find out CURRENT friending status
    friending_status, friend_button = \
        get_friending_status(browser,
                                track,
                                login,
                                userid_to_friend,
                                None,
                                logger,
                                logfolder)
    logger.info(friending_status)
    if friending_status in ["Add Friend"]:
        click_visibly(browser, Settings, friend_button)  # click to friend
        friend_state, msg = verify_action(browser, "friend", track, login,
                                            userid_to_friend, None, logger,
                                            logfolder)
        if friend_state is not True:
            return False, msg
    elif friending_status is None:
        # TODO:BUG:2nd login has to be fixed with userid of loggedin user
        sirens_wailing, emergency_state = emergency_exit(browser, Settings, "https://facebook.com", login,
                                                            login, logger, logfolder)
        if sirens_wailing is True:
            return False, emergency_state

        else:
            logger.warning(
                "--> Add Friend button not present '{}'!\t~unexpected failure".format(
                    userid_to_friend))
            return False, "unexpected failure"

    # general tasks after a successful friend
    logger.info("--> Friended '{}'!".format(userid_to_friend.encode("utf-8")))
    update_activity(Settings, 'friendeds')

    logtime = datetime.now().strftime('%Y-%m-%d %H:%M')
    log_friended_pool(login, userid_to_friend, logger,
                      logfolder, logtime, userid_to_friend)

    friend_restriction("write", userid_to_friend, None, logger)

    # if blacklist['enabled'] is True:
    #     action = 'friendeds'
    #     add_user_to_blacklist(userid_to_friend,
    #                           blacklist['campaign'],
    #                           action,
    #                           logger,
    #                           logfolder)

    # # get the post-friend delay time to sleep
    # naply = get_action_delay("friend")
    # sleep(naply)

    return True, "success"

def unfriend_user(browser, track, login, userid_to_unfriend, button, blacklist,
                logger, logfolder, sleep_delay):
    """ UnFriend a user either from the profile page or post page or dialog
    box """
    user_link = "https://www.facebook.com/{}/".format(userid_to_unfriend)
    web_address_navigator( browser, user_link, Settings)
    delay_random = random.randint(
                ceil(sleep_delay * 0.85),
                ceil(sleep_delay * 1.14))
    try:
        friend_button_elem = browser.find_element_by_css_selector("div#pagelet_timeline_profile_actions > div.FriendButton > a > span > span")
        ActionChains(browser).move_to_element(friend_button_elem).perform()
        ActionChains(browser).click().perform()
        sleep(delay_random)

        unfriend_button = browser.find_element_by_xpath("//*[contains(text(), 'Unfriend')]")
        unfriend_button.click()
        sleep(delay_random)
        return True, "success"
    except Exception as e:
        logger.error(e)
        return False, ""

    # retry_times = 0
    # while(retry_times < 10):
    #     try:
    #         sleep(delay_random)
    #         dropx, dropy = pyautogui.locateCenterOnScreen(CWD + '/pngs/unfriend.png', grayscale=True, confidence=.6)
    #         logger.info("unfriend.png is Visible, lets click it")
    #         pyautogui.moveTo(dropx, dropy)
    #         sleep(delay_random)
    #         pyautogui.click()
    #         pyautogui.doubleClick()
    #         sleep(delay_random)
    #         logger.info("unfriend.png Clicked")
    #         friend_restriction("write", userid_to_unfriend, None, logger)
    #         break
    #     except Exception as e:
    #         logger.info('unfriend.png is not yet visible. Error: {}'.format(e))
    #     retry_times = retry_times + 1
    # sleep(delay_random)
    # if retry_times < 10:
    #     return True, "success"
    # else:
    #     return False, ""

def unfriend_user_by_url(browser, track, login, url, button, blacklist,
                logger, logfolder, sleep_delay):
    """ UnFriend a user either from the profile page or post page or dialog
    box """
    web_address_navigator( browser, url, Settings)
    delay_random = random.randint(
                ceil(sleep_delay * 0.85),
                ceil(sleep_delay * 1.14))
    try:
        friend_button_elem = browser.find_element_by_css_selector("div#pagelet_timeline_profile_actions > div.FriendButton > a > span > span")
        ActionChains(browser).move_to_element(friend_button_elem).perform()
        ActionChains(browser).click().perform()
        sleep(delay_random*2)

        unfriend_button = browser.find_element_by_xpath("//*[contains(text(), 'Unfriend')]")
        unfriend_button.click()
        sleep(delay_random)
        return True, "success"
    except Exception as e:
        logger.error(e)
        return False, ""

    # sleep(delay_random)
    # retry_times = 0
    # while(retry_times < 10):
    #     try:
    #         sleep(delay_random)
    #         dropx, dropy = pyautogui.locateCenterOnScreen(CWD + '/pngs/unfriend.png', grayscale=True, confidence=.6)
    #         logger.info("unfriend.png is Visible, lets click it")
    #         pyautogui.moveTo(dropx, dropy)
    #         sleep(delay_random)
    #         pyautogui.click()
    #         pyautogui.doubleClick()
    #         sleep(delay_random)
    #         logger.info("unfriend.png Clicked")
    #         break
    #     except Exception as e:
    #         logger.info('unfriend.png is not yet visible. Error: {}'.format(e))
    #     retry_times = retry_times + 1
    # sleep(delay_random)
    # if retry_times < 10:
    #     return True, "success"
    # else:
    #     return False, ""

def friend_restriction(operation, username, limit, logger):
    """ Keep track of the friended users and help avoid excessive friend of
    the same user """

    try:
        # get a DB and start a connection
        db, id = get_database(Settings)
        conn = sqlite3.connect(db)

        with conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(
                "SELECT * FROM friendRestriction WHERE profile_id=:id_var "
                "AND username=:name_var",
                {"id_var": id, "name_var": username})
            data = cur.fetchone()
            friend_data = dict(data) if data else None

            if operation == "write":
                if friend_data is None:
                    # write a new record
                    cur.execute(
                        "INSERT INTO friendRestriction (profile_id, "
                        "username, times) VALUES (?, ?, ?)",
                        (id, username, 1))
                else:
                    # update the existing record
                    friend_data["times"] += 1
                    sql = "UPDATE friendRestriction set times = ? WHERE " \
                          "profile_id=? AND username = ?"
                    cur.execute(sql, (friend_data["times"], id, username))

                # commit the latest changes
                conn.commit()

            elif operation == "read":
                if friend_data is None:
                    return False

                elif friend_data["times"] < limit:
                    return False

                else:
                    exceed_msg = "" if friend_data[
                        "times"] == limit else "more than "
                    logger.info("---> {} has already been friended {}{} times"
                                .format(username, exceed_msg, str(limit)))
                    return True

    except Exception as exc:
        logger.error(
            "Dap! Error occurred with friend Restriction:\n\t{}".format(
                str(exc).encode("utf-8")))

    finally:
        if conn:
            # close the open connection
            conn.close()

def confirm_unfriend(browser):
    """ Deal with the confirmation dialog boxes during an unfollow """
    attempt = 0

    while attempt < 3:
        try:
            attempt += 1
            button_xp = "//button[text()='Unfollow']"  # "//button[contains(
            # text(), 'Unfollow')]"
            unfollow_button = browser.find_element_by_xpath(button_xp)

            if unfollow_button.is_displayed():
                click_element(browser, Settings, unfollow_button)
                sleep(2)
                break

        except (ElementNotVisibleException, NoSuchElementException) as exc:
            # prob confirm dialog didn't pop up
            if isinstance(exc, ElementNotVisibleException):
                break

            elif isinstance(exc, NoSuchElementException):
                sleep(1)
                pass

def get_following_status(browser, track, username, person, person_id, logger,
                         logfolder):
    """ Verify if you are following the user in the loaded page """
    if track == "profile":
        ig_homepage = "https://www.facebook.com/"
        web_address_navigator( browser, ig_homepage + person, Settings)

    follow_button_XP = ("//div/div/a[@role='button'][text()='Follow']")
    failure_msg = "--> Unable to detect the following status of '{}'!"
    user_inaccessible_msg = (
        "Couldn't access the profile page of '{}'!\t~might have changed the"
        " username".format(person))

    # check if the page is available
    valid_page = is_page_available(browser, logger, Settings)
    if not valid_page:
        logger.warning(user_inaccessible_msg)
        person_new = verify_username_by_id(browser,
                                           username,
                                           person,
                                           None,
                                           logger,
                                           logfolder)
        if person_new:
            web_address_navigator( browser, ig_homepage + person_new, Settings)
            valid_page = is_page_available(browser, logger, Settings)
            if not valid_page:
                logger.error(failure_msg.format(person_new.encode("utf-8")))
                return "UNAVAILABLE", None

        else:
            logger.error(failure_msg.format(person.encode("utf-8")))
            return "UNAVAILABLE", None

    # wait until the follow button is located and visible, then get it
    follow_button = explicit_wait(browser, "VOEL", [follow_button_XP, "XPath"],
                                  logger, 7, False)
    if not follow_button:
        browser.execute_script("location.reload()")
        update_activity(Settings)

        follow_button = explicit_wait(browser, "VOEL",
                                      [follow_button_XP, "XPath"], logger, 14,
                                      False)
        if not follow_button:
            # cannot find the any of the expected buttons
            logger.error(failure_msg.format(person.encode("utf-8")))
            return None, None

    # get follow status
    following_status = follow_button.text

    return following_status, follow_button


def verify_action(browser, action, track, username, person, person_id, logger,
                  logfolder):
    """ Verify if the action has succeeded """
    # currently supported actions are follow & unfollow

    if action in ["follow", "unfollow"]:
        if action == "follow":
            post_action_text = "//button[text()='Following' or text(" \
                               ")='Requested']"

        elif action == "unfollow":
            post_action_text = "//button[text()='Follow' or text()='Follow " \
                               "Back']"

        button_change = explicit_wait(browser, "VOEL",
                                      [post_action_text, "XPath"], logger, 7,
                                      False)
        if not button_change:
            reload_webpage(browser, Settings)
            following_status, follow_button = get_following_status(browser,
                                                                   track,
                                                                   username,
                                                                   person,
                                                                   person_id,
                                                                   logger,
                                                                   logfolder)
            # find action state *.^
            if following_status in ["Following", "Requested"]:
                action_state = False if action == "unfollow" else True

            elif following_status in ["Follow", "Follow Back"]:
                action_state = True if action == "unfollow" else False

            else:
                action_state = None

            # handle it!
            if action_state is True:
                logger.info(
                    "Last {} is verified after reloading the page!".format(
                        action))

            elif action_state is False:
                # try to do the action one more time!
                click_visibly(browser, Settings, follow_button)

                if action == "unfollow":
                    sleep(4)  # TODO: use explicit wait here
                    confirm_unfriend(browser)

                button_change = explicit_wait(browser, "VOEL",
                                              [post_action_text, "XPath"],
                                              logger, 9, False)
                if not button_change:
                    logger.warning("Phew! Last {0} is not verified."
                                   "\t~'{1}' might be temporarily blocked "
                                   "from {0}ing\n"
                                   .format(action, username))
                    sleep(210)
                    return False, "temporary block"

            elif action_state is None:
                logger.error(
                    "Hey! Last {} is not verified out of an unexpected "
                    "failure!".format(action))
                return False, "unexpected"

    return True, "success"

def get_user_id(browser, track, username, logger):
    """ Get user's ID either from a profile page or post page """
    user_id = "unknown"

    if track != "dialog":  # currently do not get the user ID for follows
        # from 'dialog'
        user_id = find_user_id(Settings, browser, track, username, logger)

    return user_id

