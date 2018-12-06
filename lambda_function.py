#!/usr/bin/env python
#
# Version 0.2
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
from urlparse import urlsplit

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
		self.headers = { 'Accept': 'application/json, text/plain, */*', 'Content-Type': 'application/json;charset=UTF-8', 'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0.1; D5803 Build/23.5.A.1.291; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/63.0.3239.111 Mobile Safari/537.36' }
		self.session = requests.Session()
		self.timeout_counter = 30 # seconds
		
		try:
			self._carnet_logon()
		except AssertionError as error:
			self.talk += "Sorry, I can't log in at this time."
			self.talk += error
		except:	
			self.talk += "Sorry, I can't log in at this time. Check credentials."

	def _carnet_logon(self):
		AUTHHEADERS = {
			'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
			'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0.1; D5803 Build/23.5.A.1.291; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/63.0.3239.111 Mobile Safari/537.36'}

		auth_base = "https://security.volkswagen.com"
		base = "https://www.volkswagen-car-net.com"

		# Regular expressions to extract data
		csrf_re = re.compile('<meta name="_csrf" content="([^"]*)"/>')
		redurl_re = re.compile('<redirect url="([^"]*)"></redirect>')
		viewstate_re = re.compile('name="javax.faces.ViewState" id="j_id1:javax.faces.ViewState:0" value="([^"]*)"')
		authcode_re = re.compile('code=([^"]*)&')
		authstate_re = re.compile('state=([^"]*)')

		def extract_csrf(r):
			return csrf_re.search(r.text).group(1)

		def extract_redirect_url(r):
			return redurl_re.search(r.text).group(1)

		def extract_view_state(r):
			return viewstate_re.search(r.text).group(1)

		def extract_code(r):
			return authcode_re.search(r).group(1)

		def extract_state(r):
			return authstate_re.search(r).group(1)

		# Request landing page and get CSFR:
		r = self.session.get(base + '/portal/en_GB/web/guest/home')
		assert (r.status_code == 200), "Car Net portal not availble (1)."
		csrf = extract_csrf(r)

		# Request login page and get CSRF
		AUTHHEADERS["Referer"] = base + '/portal'
		AUTHHEADERS["X-CSRF-Token"] = csrf
		r = self.session.post(base + '/portal/web/guest/home/-/csrftokenhandling/get-login-url', headers=AUTHHEADERS)
		assert (r.status_code == 200), "Car Net portal not availble (2)."
		responseData = json.loads(r.content)
		lg_url = responseData.get("loginURL").get("path")

		# no redirect so we can get values we look for
		r = self.session.get(lg_url, allow_redirects=False, headers = AUTHHEADERS)
		assert (r.status_code == 302), "Car Net portal not availble (3)."
		ref_url = r.headers.get("location")

		# now get actual login page and get session id and ViewState
		r = self.session.get(ref_url, headers = AUTHHEADERS)
		assert (r.status_code == 200), "Car Net portal not availble (4)."
		view_state = extract_view_state(r)

		# Login with user details
		AUTHHEADERS["Faces-Request"] = "partial/ajax"
		AUTHHEADERS["Referer"] = ref_url
		AUTHHEADERS["X-CSRF-Token"] = ''

		post_data = {
			'loginForm': 'loginForm',
			'loginForm:email': self.carnet_username,
			'loginForm:password': self.carnet_password,
			'loginForm:j_idt19': '',
			'javax.faces.ViewState': view_state,
			'javax.faces.source': 'loginForm:submit',
			'javax.faces.partial.event': 'click',
			'javax.faces.partial.execute': 'loginForm:submit loginForm',
			'javax.faces.partial.render': 'loginForm',
			'javax.faces.behavior.event': 'action',
			'javax.faces.partial.ajax': 'true'
		}

		r = self.session.post(auth_base + '/ap-login/jsf/login.jsf', data=post_data, headers = AUTHHEADERS)
		assert (r.status_code == 200), "Car Net login error."
		ref_url = extract_redirect_url(r).replace('&amp;', '&')

		# redirect to link from login and extract state and code values
		r = self.session.get(ref_url, allow_redirects=False, headers = AUTHHEADERS)
		assert (r.status_code == 302), "Car Net post login error (5)."
		ref_url2 = r.headers.get("location")

		code = extract_code(ref_url2)
		state = extract_state(ref_url2)

		# load ref page
		r = self.session.get(ref_url2, headers = AUTHHEADERS)
		assert (r.status_code == 200), "Car Net post login error (6)."

		AUTHHEADERS["Faces-Request"] = ""
		AUTHHEADERS["Referer"] = ref_url2
		post_data = {
			'_33_WAR_cored5portlet_code': code,
			'_33_WAR_cored5portlet_landingPageUrl': ''
		}
		r = self.session.post(base + urlsplit(
			ref_url2).path + '?p_auth=' + state + '&p_p_id=33_WAR_cored5portlet&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1&_33_WAR_cored5portlet_javax.portlet.action=getLoginStatus',
				   data=post_data, allow_redirects=False, headers=AUTHHEADERS)
		assert (r.status_code == 302), "Car Net post login error (7)."

		ref_url3 = r.headers.get("location")
		r = self.session.get(ref_url3, headers=AUTHHEADERS)

		# We have a new CSRF
		csrf = extract_csrf(r)

		# Update headers for requests
		self.headers["Referer"] = ref_url3
		self.headers["X-CSRF-Token"] = csrf
		self.url = ref_url3

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


