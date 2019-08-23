#!/usr/bin/env python
#
# Version 2.0
#	- Updated for WE Connect portal
#	- Fixed Google geocode location API call
#	- Corrected charging status report.
#
# Source: https://github.com/reneboer/alexa-Carnet/
# Huge thank you to https://github.com/Strosel/Carnet-alexa
#
from __future__ import print_function

import re
import json
import time

import sys, os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/' + '/modules'))
import requests
import boto3
from base64 import b64decode
#from urlparse import urlsplit
# import correct lib for python v3.x or fallback to v2.x
try: 
    import urllib.parse as urlparse
except ImportError:
    # Python 2
    import urlparse


# Get the value of an Environment Variable. 
# First see if it is encrypted for in transit, if so dycrypt.
# Return empty strin on error.
def GetAWSEnvironmentVariable(key):
	value = ""
	try:
		# Decrypt code should run once and variables stored outside of the function
		# handler so that these are decrypted once per container
		ENCRYPTED = os.environ[key]
		try:
			value = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED))['Plaintext']
		except:
			value = ENCRYPTED
	except:
		pass
	return value
	

class VWCarnet(object):
	def __init__(self, args):
		self.talk = ""
		self.carnet_username = GetAWSEnvironmentVariable('UID')
		self.carnet_password = GetAWSEnvironmentVariable('PWD')
		self.googleapikey = GetAWSEnvironmentVariable('GoogleAPIKey')
		if args['type'] == "LaunchRequest" or "InfoIntent" in args['intent']['name']:
			self.intent = "Info"
			try:
				self.carnet_task = args['intent']['name'].replace("InfoIntent","")
			except:
				self.carnet_task = ""
		elif args['type'] == "IntentRequest":
			self.intent = args['intent']['name']
			self.carnet_task = args['intent']['slots']['task']['value']
		
		print(self.carnet_username)
		if self.carnet_username == "":
			self.talk += "Your Car Net username is not configured."
			return
		if self.carnet_password == "":
			self.talk += "Your Car Net password is not configured."
			return
		
		# Fake the VW CarNet mobile app headers
		self.headers = { 
			'Accept-Encoding': 'gzip, deflate, br',
			'Accept-Language': 'en-US,nl;q=0.7,en;q=0.3',
			'Accept': 'application/json, text/plain, */*',
			'Content-Type': 'application/json;charset=UTF-8',
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:68.0) Gecko/20100101 Firefox/68.0',
			'Connection': 'keep-alive',
			'Pragma': 'no-cache',
			'Cache-Control': 'no-cache'
		}	
		self.session = requests.Session()
		self.timeout_counter = 30 # seconds
		
		try:
			self._carnet_logon()
		except AssertionError as error:
			self.talk += "Sorry, I can't log in at this time."
			self.talk += str(error)
		except StandardError as error:	
			self.talk += "Sorry, some error : "
			self.talk += str(error)
		except:	
			self.talk += "Sorry, I can't log in at this time. Check credentials."

	def _carnet_logon(self):

		def remove_newline_chars(string):
			return string.replace('\n', '').replace('\r', '')

		def extract_csrf(string):
			# Get value from HTML head _csrf meta tag.
			try:
				csrf_re = re.compile('<meta name="_csrf" content="(.*?)"/>')
				resp = csrf_re.search(string).group(1)
			except:
				resp = ''
			return resp

		def extract_login_hmac(string):
			# Get hmac value from html input form.
			try:
				regex = re.compile('<input.*?id="hmac".*?value="(.*?)"/>')
				resp = regex.search(string).group(1)
			except:
				resp = ''
			return resp

		def extract_login_csrf(string):
			# Get csrf value from html input form.
			try:
				regex = re.compile('<input.*?id="csrf".*?value="(.*?)"/>')
				resp = regex.search(string).group(1)
			except:
				resp = ''
			return resp

		def extract_url_parameter(url, cmnd):
			# Get parameter value from url.
			try:
				parsed = urlparse.urlparse(url)
				resp = urlparse.parse_qs(parsed.query)[cmnd][0]
			except:
				resp = ''
			return resp

		base_url = "https://www.portal.volkswagen-we.com"
		auth_base_url = 'https://identity.vwgroup.io'
		
		# Step 1, Request landing page and get CSRF:
		landing_page_url = base_url + '/portal/en_GB/web/guest/home'
		landing_page_response = self.session.get(landing_page_url)
		assert (landing_page_response.status_code == 200), "WE Connect portal not availble (1)."
		csrf = extract_csrf(landing_page_response.text)
		assert (csrf != ''), 'Failed to get CSRF from landing page (1).'

		# Step 2, Get login page url. POST returns JSON with loginURL for next step.
		auth_request_headers = {
			'Accept-Encoding': 'gzip, deflate, br',
			'Accept-Language': 'en-US,nl;q=0.7,en;q=0.3',
			'Accept': 'text/html,application/xhtml+xml,application/xml,application/json;q=0.9,*/*;q=0.8',
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:68.0) Gecko/20100101 Firefox/68.0',
			'Connection': 'keep-alive',
			'Pragma': 'no-cache',
			'Cache-Control': 'no-cache'
		}
		auth_request_headers['Referer'] = landing_page_url
		auth_request_headers['X-CSRF-Token'] = csrf
		get_login_url = base_url + '/portal/en_GB/web/guest/home/-/csrftokenhandling/get-login-url'
		login_page_response = self.session.post(get_login_url, headers=auth_request_headers)
		assert (login_page_response.status_code == 200), "WE Connect portal not availble (2)."
		try:
			login_url = json.loads(login_page_response.text).get('loginURL').get('path')
		except:	
			login_url = ''
		assert (login_url != ''), 'Failed to get login_url (2).'
		client_id = extract_url_parameter(login_url, 'client_id')
		assert (client_id != ''), 'Failed to get client_id (2).'

		# Step 3, Get login form url we are told to use, it will give us a new location.
		login_url_response = self.session.get(login_url, allow_redirects=False, headers=auth_request_headers)
		assert (login_url_response.status_code == 302), "WE Connect portal not availble (3)."
		login_form_url = login_url_response.headers.get('location')
		login_relay_state_token = extract_url_parameter(login_form_url, 'relayState')
		assert (login_form_url != ''), 'Failed to get login form url (3).'
		assert (login_relay_state_token != ''), 'Failed to get relay State (3).'

		# Step 4, Get login action url, relay state. hmac token 1 and login CSRF from form contents
		login_form_location_response = self.session.get(login_form_url, headers=auth_request_headers)
		assert (login_form_location_response.status_code == 200), "WE Connect portal not availble (4)."
		login_form_location_response_data = remove_newline_chars(login_form_location_response.text)
		hmac_token1 = extract_login_hmac(login_form_location_response_data)
		login_csrf = extract_login_csrf(login_form_location_response_data)
		assert (login_csrf != ''), 'Failed to get login form csrf (4).'
		assert (hmac_token1 != ''), 'Failed to get login form hmac token (4).'

		# Step 5, Post identifier data
		del auth_request_headers['X-CSRF-Token']
		auth_request_headers['Referer'] = login_form_url
		auth_request_headers['Content-Type'] = 'application/x-www-form-urlencoded'
		post_data = {
			'email': self.carnet_username,
			'relayState': login_relay_state_token,
			'hmac': hmac_token1,
			'_csrf': login_csrf,
		}
		login_action_url = auth_base_url + '/signin-service/v1/' + client_id + '/login/identifier'
		login_action_url_response = self.session.post(login_action_url, data=post_data, headers=auth_request_headers, allow_redirects=True)
		assert (login_action_url_response.status_code == 200), "WE Connect portal not availble (5)."
		auth_request_headers['Referer'] = login_action_url
		auth_request_headers['Content-Type'] = 'application/x-www-form-urlencoded'
		login_action2_url = auth_base_url + '/signin-service/v1/' + client_id + '/login/authenticate'
		login_action_url_response_data = remove_newline_chars(login_action_url_response.text)
		hmac_token2 = extract_login_hmac(login_action_url_response_data)
		assert (hmac_token2 != ''), 'Failed to get login form hmac token (5).'

		# Step 6, Post login data to authenticate
		login_data = {
			'email': self.carnet_username,
			'password': self.carnet_password,
			'relayState': login_relay_state_token,
			'hmac': hmac_token2,
			'_csrf': login_csrf,
			'login': 'true'
		}
		login_post_response = self.session.post(login_action2_url, data=login_data, headers=auth_request_headers, allow_redirects=True)
		assert (login_post_response.status_code == 200), "WE Connect portal not availble (6)."
		ref2_url = login_post_response.url                      
		portlet_code = extract_url_parameter(ref2_url, 'code')
		state = extract_url_parameter(ref2_url, 'state')
		assert (portlet_code != ''), 'Failed to get portlet_code (6).'
		assert (state != ''), 'Failed to get login state (6).'

		# Step 7 Post login data to complete login url
		auth_request_headers['Referer'] = ref2_url
		portlet_data = {'_33_WAR_cored5portlet_code': portlet_code}
		final_login_url = base_url + '/portal/web/guest/complete-login?p_auth=' + state +        '&p_p_id=33_WAR_cored5portlet&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&_33_WAR_cored5portlet_javax.portlet.action=getLoginStatus'
		complete_login_response = self.session.post(final_login_url, data=portlet_data, allow_redirects=False, headers=auth_request_headers)
		assert (complete_login_response.status_code == 302), "WE Connect portal not availble (7)."
		base_json_url = complete_login_response.headers.get('location')
		assert (base_json_url != ''), 'Failed to get base portal url (7).'

		# Step 8 Get base JSON url for commands 
		base_json_response = self.session.get(base_json_url, headers=auth_request_headers)
		assert (base_json_response.status_code == 200), "WE Connect portal not availble (8)."
		csrf = extract_csrf(base_json_response.text)
		assert (csrf != ''), 'Failed to get final CSRF (8).'

		# Update headers for requests
		self.headers["Referer"] = base_json_url
		self.headers["X-CSRF-Token"] = csrf
		self.url = base_json_url

	def _carnet_post(self, command):
		r = self.session.post(self.url + command, headers = self.headers)
		return r.content

	def _carnet_post_action(self, command, data):
		r = self.session.post(self.url + command, json=data, headers = self.headers)
		return r.content


	def _carnet_retrieve_carnet_info(self):
		vehicle_data = {}

		vehicle_data_status = json.loads(self._carnet_post('/-/vsr/get-vsr'))
		vehicle_data_details = json.loads(self._carnet_post('/-/vehicle-info/get-vehicle-details'))
		vehicle_data_emanager = json.loads(self._carnet_post('/-/emanager/get-emanager'))
		vehicle_data_location = json.loads(self._carnet_post('/-/cf/get-location'))

		vehicle_data['status'] = vehicle_data_status
		vehicle_data['details'] = vehicle_data_details
		vehicle_data['emanager'] = vehicle_data_emanager
		vehicle_data['location'] = vehicle_data_location

		return vehicle_data

	def _carnet_start_charge(self):
		post_data = {
			'triggerAction': True,
			'batteryPercent': '100'
		}
		return json.loads(self._carnet_post_action('/-/emanager/charge-battery', post_data))

	def _carnet_stop_charge(self):
		post_data = {
			'triggerAction': False,
			'batteryPercent': '99'
		}
		return json.loads(self._carnet_post_action('/-/emanager/charge-battery', post_data))


	def _carnet_start_climat(self):
		post_data = {
			'triggerAction': True,
			'electricClima': True
		}
		return json.loads(self._carnet_post_action('/-/emanager/trigger-climatisation', post_data))


	def _carnet_stop_climat(self):
		post_data = {
			'triggerAction': False,
			'electricClima': True
		}
		return json.loads(self._carnet_post_action('/-/emanager/trigger-climatisation', post_data))

	def _carnet_start_window_melt(self):
		post_data = {
			'triggerAction': True
		}
		return json.loads(self._carnet_post_action('/-/emanager/trigger-windowheating', post_data))

	def _carnet_stop_window_melt(self):
		post_data = {
			'triggerAction': False
		}
		return json.loads(self._carnet_post_action('/-/emanager/trigger-windowheating', post_data))

	def _carnet_print_carnet_info(self):
		vehicle_data = self._carnet_retrieve_carnet_info()
		# Get charging details
		chargestate = ""
		chargetime = ""
		try:
			if vehicle_data['emanager']['EManager']['rbc']['status']['chargingState'] == "CHARGING":
				chargestate = "charging"
				if vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningHour'] != "0":
					chargetime += vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningHour']+" hour"
					if vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningHour'] != "1":
						chargetime += "s"
				if vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningMinute'] != "00":
					if chargetime != "":
						chargetime += " and "	
					chargetime += vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningMinute']+" minute"
					if vehicle_data['emanager']['EManager']['rbc']['status']['chargingRemaningMinute'] != "1":
						chargetime += "s"
			else:
				chargestate = "not charging"
				if vehicle_data['emanager']['EManager']['rbc']['status']['extPowerSupplyState'] == "AVAILABLE" and vehicle_data['emanager']['EManager']['rbc']['status']['pluginState'] == "CONNECTED":
					chargestate += ", but ready to"
		except:
			pass
		# Get windows heating status	
		windowstate = "not heating"
		if vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateFront'] != "OFF" and vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateRear'] != "OFF":
			windowstate = "heating in the front and rear"
		elif vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateFront'] == "OFF" and vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateRear'] != "OFF":
			windowstate = "heating in the rear"
		elif vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateFront'] != "OFF" and vehicle_data['emanager']['EManager']['rpc']['status']['windowHeatingStateRear'] == "OFF":
			windowstate = "heating in the front"
		# Create response string for the intent.
		if self.carnet_task == "":
			self.talk += "Your car has driven "+str(vehicle_data['details']['vehicleDetails']['distanceCovered']).replace('.','')+"km, "
			if chargestate == "charging":
				self.talk += "The battery is charging and currently at "+str(vehicle_data['emanager']['EManager']['rbc']['status']['batteryPercentage'])+"%, "
			else:
				self.talk += "The battery is at "+str(vehicle_data['emanager']['EManager']['rbc']['status']['batteryPercentage'])+"%, " 
			self.talk += "The climate-control is "+str(vehicle_data['emanager']['EManager']['rpc']['status']['climatisationState'])+", Windows are "+windowstate+". "
		elif self.carnet_task == "Location":
			addr = self._google_get_location(str(vehicle_data['location']['position']['lng']), str(vehicle_data['location']['position']['lat']))
			self.talk += "Your car is located at "+addr+". "
		elif self.carnet_task == "Battery":
			self.talk += "Your car's battery is currently at "+str(vehicle_data['emanager']['EManager']['rbc']['status']['batteryPercentage'])+"%. "
		elif self.carnet_task == "Charge":
			if chargestate != "":
				self.talk += "Your car is "+chargestate
				if chargetime != "":
					self.talk += ", The battery is at "+str(vehicle_data['emanager']['EManager']['rbc']['status']['batteryPercentage'])+"%"
					self.talk += ", The remaining charge time is "+chargetime
				self.talk += ". "
			else:
				self.talk += "Your car is not charging. "
		elif self.carnet_task == "Heat":
			self.talk += "Your car's climate-control is "+str(vehicle_data['emanager']['EManager']['rpc']['status']['climatisationState'])+" and Windows are "+windowstate+". "
		elif self.carnet_task == "Distance":
			self.talk += "Your car has driven "+str(vehicle_data['details']['vehicleDetails']['distanceCovered']).replace('.','')+"km. "
		elif self.carnet_task == "Doors":
			doorstate = "I cannot obtain the actual status."
			if vehicle_data['status']['vehicleStatusData']['lockData']['left_front'] == 2 and vehicle_data['status']['vehicleStatusData']['lockData']['right_front'] == 2:
				doorstate = "locked"
			elif vehicle_data['status']['vehicleStatusData']['lockData']['left_front'] == 3 or vehicle_data['status']['vehicleStatusData']['lockData']['right_front'] == 3:
				doorstate = "unlocked"
			self.talk += "Your car doors are "+doorstate+". "
			if vehicle_data['status']['vehicleStatusData']['lockData']['trunk'] == 3:
				self.talk += "Your car trunk is unlocked. "
		elif self.carnet_task == "Range":
			self.talk += "Your car can drive "+str(vehicle_data['emanager']['EManager']['rbc']['status']['electricRange']).replace('.','')+" km on current battery charge. "
		elif self.carnet_task == "Lights":
			if vehicle_data['status']['vehicleStatusData']['carRenderData']['parkingLights'] == 2:
				self.talk += "Your car parkinglights are off. "
			else:	
				self.talk += "Your car parkinglights are on. "
		else:
			self.talk += "Sorry, i couldnt get that information right now. "

	def _carnet_print_action(self, resp):
		if not 'actionNotification' in resp:
			self.talk += "Sorry, I can't do that right now"
		else:
			if self.intent == "StartTaskIntent":
				self.talk += "I started %s for you" % (self.carnet_task)
			elif self.intent == "StopTaskIntent":
				self.talk += "I stopped %s for you" % (self.carnet_task)

	def _carnet_do_action(self):
		if self.intent == "Info":
			self._carnet_print_carnet_info()
			return True
		elif self.intent == "StartTaskIntent":
			if 'charg' in self.carnet_task:
				resp = self._carnet_start_charge()
				self._carnet_print_action(resp)
				return True

			elif 'climat' in self.carnet_task or ('heat' in self.carnet_task and 'window' not in self.carnet_task):
				resp = self._carnet_start_climat()
				self._carnet_print_action(resp)
				return True

			elif 'window' in self.carnet_task:
				resp = self._carnet_start_window_melt()
				self._carnet_print_action(resp)
				return True
			else:
				self.talk = "I didn't quite get that"
				return True
		elif self.intent == "StopTaskIntent":
			if 'charg' in self.carnet_task:
				resp = self._carnet_stop_charge()
				self._carnet_print_action(resp)
				return True

			elif 'climat' in self.carnet_task or ('heat' in self.carnet_task and 'window' not in self.carnet_task):
				resp = self._carnet_stop_climat()
				self._carnet_print_action(resp)
				return True

			elif 'window' in self.carnet_task:
				resp = self._carnet_stop_window_melt()
				self._carnet_print_action(resp)
				return True
			else:
				self.talk = "I didn't quite get that"
				return True

	# API call is obsolete
	def _google_get_location(self, lng, lat):
		counter = 0
		location = "unknown"
		print(self.googleapikey, lat, lng)
		if self.googleapikey == "":
			return location
		while counter < 3:
			lat_reversed = str(lat)[::-1]
			lon_reversed = str(lng)[::-1]
			lat = lat_reversed[:6] + lat_reversed[6:]
			lon = lon_reversed[:6] + lon_reversed[6:]
			print(str(lat[::-1]) + ',' + str(lon[::-1]))
			try:
				req = requests.get('https://maps.googleapis.com/maps/api/geocode/json?latlng=' + str(lat[::-1]) + ',' + str(lon[::-1])+'&result_type=street_address&key='+self.googleapikey)
			except:
				counter += 1
				time.sleep(2)
				continue
			
			data = json.loads(req.content)
			if 'status' in data and data['status'] == 'OK':
				location = data["results"][0]["formatted_address"]
				break

			time.sleep(2)
			counter += 1
			continue

		return location

def post_waitmessage(req, cnxt):
	# check request type
	if req['type'] == "LaunchRequest" or req['type'] == "IntentRequest":
		try:
			token = cnxt['System']['apiAccessToken']
			endPoint = cnxt['System']['apiEndpoint']
			requestID = req['requestId']
			hdrs = { 'Authorization': 'Bearer '+token, 'Content-Type': 'application/json' }
			dt = { 'header': { 'requestId': requestID }, 'directive': { "type":"VoicePlayer.Speak", "speech":"Please hold while your car is contacted."} }
			requests.post (endPoint+'/v1/directives', headers=hdrs, data=json.dumps(dt))
		except:	
			print("failed to send directive.")
	else:
		print("Request type does not support a directive: "+request.type)
	return True	

def main(event, context):

	post_waitmessage(event['request'], event['context'])
	vw = VWCarnet(event['request'])
	if vw.talk == "":
		try:
			print("logged on, execute action :")
			vw._carnet_do_action()
		except:    
			vw.talk = "no reply from volkswagen."
	response = {
		"version": "1.0",
		"response": {
			"outputSpeech": {
				"type": "SSML",
				"ssml": "<speak>"+vw.talk+"</speak>",
			}
		}
	}
	return response


