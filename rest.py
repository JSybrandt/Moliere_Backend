#!/usr/bin/env python
import web
import xml.etree.ElementTree as ET
import json
import pymssql
import datetime
import time
import boto3
import botocore
import requests
import pprint


# TO RUN SERVER:
# python .\rest.py 10.100.0.207

#PUBLIC
# IP: 34.230.125.24
# DNS: ec2-34-230-125-24.compute-1.amazonaws.com

#PRIVATE
# IP: 10.100.0.207
# DNS: ip-10-100-0-207.ec2.internal

#TODO:
# Actually delete results on DELETE request to /results
 

# Useful tools
#
# POSTMAN - It's amazing and gives you nerdy jokes every time you open it
# 	- It will save you hours
# BOTO 3
#	- Amazon SDK for Python


# tree = ET.parse('user_data.xml') ### USED IN XML PARSING
# root = tree.getroot() ### USED IN XML PARSING

## URLS - used to match requests to appropriate class functions
urls = (
	'/jobs', 'jobs',
	'/jobs/(.*)', 'jobs',
	'/results/(.*)', 'results'
	,'/status/(.*)', 'status' ## DEBUG
#    '/users', 'list_users',    ### USED IN XML PARSING
#    '/users/(.*)', 'get_user', ### USED IN XML PARSING
)

publicIP = '34.230.125.24:8080'

# Register app variable
app = web.application(urls, globals())

# sqlconn() - returns a connection to our Job_DB database
#             Example usage: conn = sqlconn()
def sqlconn():
	return pymssql.connect(server='jobdatabase.cytfqcno5uiv.us-east-1.rds.amazonaws.com',port='1433',user='JobAdmin',password='AdminPassJobs',database='Job_DB')

	
# respond() - used at the end of every request to return appropriate response.
#             Example usage: return respond(web, r404) # Returns 404 Not Found
#
#   returns: '' - Blank http body. To return a JSON string, use respond_dict()
#
#   web - web variable provided in the class method
#   status - string representing return status code. EX: r404 (global string variable representing '404 Not Found'
def respond(web, status):
	web.ctx.status = status
	print('\n<Empty http response>')
	return ''

# respond_dict() - like respond(), but prints a dictionary as a JSON string in the HTTP body
#                  Example usage: return respond_dict(web, r200, results_dict) # Returns 404 Not Found
#
#   returns: JSON string representing contents of dictionary provided
#
#   web - web variable provided in the class method
#   status - string representing return status code. EX: r404 (global string variable representing '404 Not Found'
#   dicty - dictionary containing entries to return in HTTP body
def respond_dict(web, status, dicty):
	web.ctx.status = status
	ret = json.dumps(dicty)
	print('\n'+ret)
	return ret

# respond_see_other() - like respond(), but returns returns 303 and sets the location header to the specified URL
#                       Example usage: return respond_see_other(web, url) # Returns 303 See other
#
#   returns: empty string variable
#
#   web - web variable provided in the class method
#   url - the url that contains other
def respond_see_other(web, url):
	web.ctx.status = r303
	web.header('Location', url)
	
	print('\nSee other - ' + url)
	return ''

# dictFromResults() - creates a dictionary variable from a SQL results row variable
#                     Example usage: results_dict = dictFromResults(sqlRow)
#
#   returns: A dictionary variable that meets the HTTP body response standards set in the intercommunications API
#
#   row - A single row of results from an SQL call
def dictFromResults(row):
	id = row[0]
	word1 = row[1]
	word2 = row[2]
	dateCreated = row[3]
	lastUpdated = row[4]
	jobStatus = row[5]
	
	dicty = {"jobID":id, "word1":word1, "word2":word2, "created":dateCreated.isoformat(), "update":lastUpdated.isoformat(), "status":jobStatus.strip()}
	
	return dicty

# formatBadRequest() - Returns a dictionary which represents the HTTP response to a bad request.
#                      Example usage: response_dict = formatBadRequest(web.data())
#
#   returns: A dictionary variable that meets the HTTP body response standards set in the intercommunications API
#
#   data - The request given by the user. Generally found by calling web.data()
def formatBadRequest(data):
	return {'reason': 'Invalid request given. Request: ' + str(data)}
	
# isInvalidID() - Returns true if the jobID given is invalid, false otherwise
#                 Example usage: if isInvalidID(jobID): <return 400 Bad Request>
#
#   returns: Returns true if the jobID given is invalid, false otherwise
#
#   id - job ID given by the user
def isInvalidID(id):
	CONST_MAX_ID = 2147483647
	
	# Confirm ID is a number. If not, return false
	# Necessary to avoid decimals being accepted
	if not id.isdigit():
		return True
		
	try:
		testint = int(id)
		
		if testint > CONST_MAX_ID: # Too big - return not found (if value is bigger than max int value, we'll get an int overflow exception in SQL)
			return True
			
	except Exception as e:
		# Something horrible happened - ID is invalid
		return True

	return False

# Returns a string representing the URL used to access the public S3 bucket of the provided ID
def resultsUrl(id):
	return 'https://s3.amazonaws.com/results-moliere/CSV_Results/' + str(id) + '.txt'

# Hacky method which checks to see if the results exist for a given job ID
def areResultsThere(id):
	url = resultsUrl(id)
	request = requests.get(url)
	if request.status_code != 404:
		#print('Web site exists')
		return True
	else:
		#print('Web site does not exist') 
		return False

# getClient() - Returns a boto3 batch client for use in the moliere system
def getClient():
	return boto3.client('batch',
			region_name='us-east-1',
			endpoint_url='http://batch.us-east-1.amazonaws.com')

# cancelJob() - Cancels the provided job from the S3 queue
#               (Assumes id is a valid ID)
#
# returns TRUE if job was cancelled
# returns FALSE otherwise
def cancelJob(id):

	try:
		conn = sqlconn()
		cursor = conn.cursor()

		# Retrieve s3 ID from sql table.
		cursor.execute('SELECT jobID, s3ID FROM s3ID WHERE jobID = %s', (id,)) # Sanitize user input
		row = cursor.fetchone()

		if cursor.rowcount == 0:
			# Row not found - Fail, return 404 Not Found
			return false

		s3ID = str(row[1])

		client = getClient()

		# Call terminate_job with proper credentials
		response = client.terminate_job(
			jobId=s3ID,
			reason='User cancelled operation'
			)

		# Job was successfully cancelled - return True
		return True
		
	except:
		# Any exception occurred - return false
		return False

# submitJob() - submits a job to the S3 queue to be run
#
# word1 - the first word to use in the algorithm. Example: 'Brain Damage'
# word2 - the second word to use in the algorithm. Example: 'Chronic Pain'
# id - The jobID of the job. Example: 71
#
# Returns - string representing s3 ID of job created. (Returns empty string if job was not created)
#			Example: 'ecd97531-8a5f-4337-92b9-bbbc7f87d3f0'
def submitJob(word1, word2, id):
	try:
		id = str(id)
		client = getClient()
		
		jobresponse = client.submit_job(
			jobName=id,
			jobQueue='queue',
			jobDefinition='compute',
			containerOverrides=
			{
				'environment': [
					{
						'name': 'BATCH_FILE_S3_URL',
						'value': 's3://script-moliere/myscript.sh'
					},
					{
						'name': 'BATCH_FILE_TYPE',
						'value': 'script'
					},
					{
						'name': 'SOURCE_WORD',
						'value': word1.replace(' ', '_') # Sanitize spaces
					},
					{
						'name': 'TARGET_WORD',
						'value': word2.replace(' ', '_') # Sanitize spaces
					},
					{
						'name': 'JOB_ID',
						'value': id
					}
				]
			})
		
		# Job was submitted - return s3 ID
		return jobresponse['jobId']
	
	except:
		# Any problem occurred - return empty string
		return ''

# s3Status() - returns string representing s3 status of job with given ID. (Returns empty string if such ID does not exist)
#              Example return value' 'RUNNING'
#
# id - ID of job you want S3 status for
# cursor - the connection cursor variable used in SQL communications
def s3Status(id, cursor):
	cursor.execute('SELECT jobID, s3ID FROM s3ID WHERE jobID = %s', (id,)) # Sanitize user input
	row = cursor.fetchone()

	if cursor.rowcount == 0:
		# Row not found - Fail, return 404 Not Found
		return ''

	s3ID = str(row[1])
	
	client = getClient()
	
	# client.describe_jobs() returns an enormous maze of a dictionary.
	# Navigate this dictionary to find the S3 status of the job
	status = client.describe_jobs(jobs=[s3ID])['jobs'][0]['status']
	
	return status

# getSQLRow() - returns a single row from the SQL table that represents the job with the given ID
#
# id - ID of job requested
# cursor - the connection cursor variable used in SQL communications
def getSQLRow(id, cursor):
	cursor.execute('SELECT jobID, word1, word2, dateCreated, lastUpdated, jobStatus FROM JobInformation WHERE jobID = %s', (id,)) # Sanitize user input
	row = cursor.fetchone()
	return row

# getSQLRow() - updates a single row from the SQL table that represents the job with the given ID
#
# newStatus - the new status for the given job
# id - ID of job requested
# conn - connection variable used in SQL communications
# cursor - the connection cursor variable used in SQL communications

def updateSQLRow(newStatus, id, conn, cursor):
	cursor.execute('UPDATE JobInformation SET jobStatus = %s WHERE jobID = %s', (newStatus, id)) # Sanitize input
	conn.commit()
	



# API numbers and their meanings
#1. Queued
#2. Running
#3. Paused
#4. Failed
#5. Completed
#6. Cancelled	

# Possible S3 values and their closest-corresponding API number
#1. SUBMITTED
#1. PENDING
#1. RUNNABLE
#2. STARTING
#2. RUNNING
#5. SUCCEEDED
#4. FAILED

s3Dict = {
	'SUBMITTED': '1',
	'PENDING': '1',
	'RUNNABLE': '1',
	'STARTING': '2',
	'RUNNING': '2',
	'SUCCEEDED': '5',
	'FAILED': '4'
	}

# decodeS3Status() - Transforms an s3 status string into a string compatible with the intercommunications API
# s - Amazon S3 status code. Example: 'RUNNING'
def decodeS3Status(s):
	assert s in s3Dict
	return s3Dict[s]


# Various URLs and locations
#	results moliere/myscript/csv_results
#	compute_results
# 's3://results-moliere/Computer_Results/' # Regular
# 's3://results-moliere/CSV_Results/' # JSON

# Response status code string variables
r200 = '200 OK'
r202 = '202 Accepted'
r303 = '303 See Other'
r400 = '400 Bad Request'
r404 = '404 Not Found'
r401 = '401 Unauthorized'
r410 = '410 Gone'
r500 = '500 Internal Server Error'

# Status variables
sQueued = '1'
sRunning = '2'
sPaused = '3'
sFailed = '4'
sCompleted = '5'
sCancelled = '6'

# DEBUG FUNCTION!! Used to foribly set the status of any give job.
# Body is 1 int - NOT JSON
class status:
	def POST(self, id):
		if(isInvalidID(id)):
			# Invalid ID - Return 400 Bad Request
			dicty = formatBadRequest(id) # Create bad request string from the id provided by end-user
			return respond_dict(web, r400, dicty) # Return 400 Bad Request
			
		newStatus = web.data()
		
		if(isInvalidID(newStatus)):
			dicty = formatBadRequest(newStatus)
			return respond_dict(web, r400, dicty) # Return 400 Bad Request

		# ID is valid - do sql work
		conn = sqlconn()
		cursor = conn.cursor()
		
		# Get requested row - see if it exists
		#print('SELECT jobID, word1, word2, dateCreated, lastUpdated, jobStatus FROM JobInformation WHERE jobID = ' + id)
		#cursor.execute('SELECT jobID, word1, word2, dateCreated, lastUpdated, jobStatus FROM JobInformation WHERE jobID = %s', (id,)) # Sanitize user input
		#row = cursor.fetchone()
		
		row = getSQLRow(id, cursor)
		
		if cursor.rowcount == 0:
			# Row not found - Fail, return 404 Not Found
			return respond(web, r404)

		#cursor.execute('UPDATE JobInformation SET jobStatus = %s WHERE jobID = %s', (newStatus, id)) # Sanitize input
		#conn.commit()
		updateSQLRow(newStatus, id, conn, cursor)
		
		return respond(web, r200)		


# Handles all requests to the 'jobs' subdirectory
class jobs:

	# POST request to jobs : request for new job, with word1 and word2 as keywords in JSON
	# Handles 202 Accepted and 400 Bad Request
	def POST(self):
	
		data = web.data(); # Get data sent with POST
		j = {};
		word1 = ''
		word2 = ''
		try:
			# Attempt to load JSON data sent in body of POST request
			j = json.loads(data); # Parse data sent with POST
			word1 = j['word1']; # Extract words 1 and 2
			word2 = j['word2'];
		except:
			# Error parsing json request or reading word1/word2 - return 400 Bad Request
			dicty = formatBadRequest(data)
			return respond_dict(web, r400, dicty)
		
		# Execute SQL commands
		conn = sqlconn()
		cursor = conn.cursor()
		cursor.execute('INSERT INTO JobInformation (word1, word2, jobStatus) VALUES (%s, %s, %s)', (word1, word2, sQueued)) # Sanitize input
		conn.commit()

		# Retrieve row just created (necessary to find jobID)
		# Don't call helper function - special functionality
		cursor.execute('SELECT TOP 1 jobID, word1, word2, dateCreated, lastUpdated, jobStatus FROM JobInformation WHERE word1 = %s AND word2 = %s ORDER BY lastUpdated DESC', (word1, word2)) # Sanitize user input
		row = cursor.fetchone()
				
		# Create API-friendly dictionary from results row to return as body of HTTP response
		dicty = dictFromResults(row)

		id = dicty['jobID']

		# Submit job to Amazon and retrieve s3 ID of created job
		s3ID = submitJob(word1, word2, id)
		
		# Job could not be created - return 500
		if s3ID == '':
			updateSQLRow(sCancelled, id, conn, cursor)
			dicty = {'reason': 'Amazon webservice could not create job ' + id}
			return respond_dict(web, r500, dicty)

		# Insert s3ID into table
		cursor.execute('INSERT INTO s3ID (jobID, s3ID) VALUES (%s, %s)', (id, s3ID)) # Sanitize input
		conn.commit()
		
		# Return 202 Accepted, with results as JSON string in body
		return respond_dict(web, r202, dicty)
		

	# GET request to jobs : Lookup status of job with given ID
	def GET(self, id):
		if(isInvalidID(id)):
			# Invalid ID - Return 400 Bad Request
			dicty = formatBadRequest(id) # Create bad request string from the id provided by end-user
			return respond_dict(web, r400, dicty) # Return 400 Bad Request

		# Request was OK - do SQL work
		conn = sqlconn()
		cursor = conn.cursor()
		
		# Get requested row
		#cursor.execute('SELECT jobID, word1, word2, dateCreated, lastUpdated, jobStatus FROM JobInformation WHERE jobID = %s', (id,)) # Sanitize user input
		#row = cursor.fetchone()
		row = getSQLRow(id, cursor)
		
		if cursor.rowcount == 0:
			# Row not found - Fail, return 404 Not Found
			return respond(web, r404)
			
		else:
			# Row found - continue
			
			# Get s3 Status of the job
			jobStatus = s3Status(id, cursor)
			
			# Job status wasn't found - return 404
			if not jobStatus:
				return respond(web, r404)
			
			# Decode jobStatus into API-friendly status
			jobStatus = decodeS3Status(jobStatus)

			# Update the SQL table with new data
			updateSQLRow(jobStatus, id, conn, cursor)

			row = getSQLRow(id, cursor)
			dicty = dictFromResults(row)
			
			# Check status of job
			# Completed - return 303 See Other, set other location to '/results/<str(jobID)>'
			if jobStatus == sCompleted:
				jobID = dicty['jobID']
				return respond_see_other(web, resultsUrl(jobID))
				
			# Failed or Cancelled - Return 410 Gone
			elif jobStatus == sFailed or jobStatus == sCancelled:
				return respond_dict(web, r410, dicty)
				
			# Any other result - Job isn't done, return 200 OK
			else:
				return respond_dict(web, r200, dicty)


	# DELETE request to jobs : Cancel job with given ID
	def DELETE(self, id):
		if(isInvalidID(id)):
			# Invalid ID - Return 400 Bad Request
			dicty = formatBadRequest(id) # Create bad request string from the id provided by end-user
			return respond_dict(web, r400, dicty) # Return 400 Bad Request

		# ID is valid - do sql work
		conn = sqlconn()
		cursor = conn.cursor()
		
		# Get requested row - see if it exists
		#cursor.execute('SELECT jobID, word1, word2, dateCreated, lastUpdated, jobStatus FROM JobInformation WHERE jobID = %s', (id,)) # Sanitize user input
		#row = cursor.fetchone()
		row = getSQLRow(id, cursor)

		if cursor.rowcount == 0:
			# Row not found - Fail, return 404 Not Found
			return respond(web, r404)
			
		dicty = dictFromResults(row)

		# Row exists - check status
		if dicty['status'] == sCancelled or dicty['status'] == sFailed:
			# Already cancelled - return 200 OK
			return respond_dict(web, r200, dicty)
			
		elif dicty['status'] == sCompleted:
			# Already completed - cannot cancel job
			# TODO: More appropriate status code?
			# print('TODO: Attempting to cancel job that is already completed. Need more appropriate response code than 200 OK');
			return respond_dict(web, r200, dicty)

		# Job has not finished running: Do job cancel procedures
		if not cancelJob(id):
			dicty = {'reason': 'S3 error: Amazon could not cancel job ' + id}
			return respond_dict(web, r500, dicty)

		# Job was successfully cancelled - Update SQL row
		#cursor.execute('UPDATE JobInformation SET jobStatus = %s WHERE jobID = %s', (sCancelled, id)) # Sanitize input
		#conn.commit()
		updateSQLRow(sCancelled, id, conn, cursor)
		
		# Respond 200 OK
		dicty['status'] = sCancelled
		return respond_dict(web, r200, dicty)


class results:

	# GET results - retrieve url for results bucket containing results
	def GET(self, id):
		if(isInvalidID(id)):
			# Invalid ID - Return 400 Bad Request
			dicty = formatBadRequest(id) # Create bad request string from the id provided by end-user
			return respond_dict(web, r400, dicty) # Return 400 Bad Request

		# Request was OK - do SQL work
		conn = sqlconn()
		cursor = conn.cursor()
		
		jobStatus = s3Status(id, cursor)
		
		# Job status wasn't found - return 404
		if not jobStatus:
			return respond(web, r404)

		# Transform job status into API-friendly status
		jobStatus = decodeS3Status(jobStatus)

		# Update SQL table with latest status
		updateSQLRow(jobStatus, id, conn, cursor)

		row = getSQLRow(id, cursor)
		dicty = dictFromResults(row)

		if cursor.rowcount == 0:
			# Row not found - Fail, return 404 Not Found
			return respond(web, r404)
			
		else:
			# Row found - continue
			
			# Create dictionary from results row
			dicty = dictFromResults(row)
			jobStatus = dicty['status']
			
						
			# Check to see if results are there or not
			if areResultsThere(id):
				# Results exist - return link to results
				return respond_see_other(web, resultsUrl(id))
			else:
				# No results yet - Check status to see if Completed
				if jobStatus == sCompleted:
					# Job was completed but no results exist - return 410 Gone
					return respond_dict(web, r410, dicty)
				else:
					# Job not completed and no results exist - return 404 Not Found
					return respond(web, r404)

	# Delete results - Deletes the results of a given id
	def DELETE(self, id):
		if(isInvalidID(id)):
			# Invalid ID - Return 400 Bad Request
			dicty = formatBadRequest(id) # Create bad request string from the id provided by end-user
			return respond_dict(web, r400, dicty) # Return 400 Bad Request

		# Request was OK - do SQL work
		conn = sqlconn()
		cursor = conn.cursor()
		
		# Get s3 status of job
		jobStatus = s3Status(id, cursor)
		
		# Job status wasn't found - return 404
		if not jobStatus:
			return respond(web, r404)

		# Decode job status into API-friendly status
		jobStatus = decodeS3Status(jobStatus)

		# Update SQL table with latest results
		updateSQLRow(jobStatus, id, conn, cursor)

		row = getSQLRow(id, cursor)
		
		if cursor.rowcount == 0:
			# Row not found - Fail, return 404 Not Found
			return respond(web, r404)
			
		else:
			# Row found - continue
			dicty = dictFromResults(row)

			# Check to see if results are there or not
			if not areResultsThere(id):
				# No results - Already deleted, return 200 OK
				return respond_dict(web, r200, dicty)
					
			else:
				# Results exist - delete results
				# TODO: Actually delete results
				# Would delete reults using client variable.
				# 1. Look up s3ID of job provided
				# 2. Use client to cancel job of s3 ID				
				print('TODO: Actually delete results for job ' + id)
				dicty = {'reason': 'Results deletion has not yet been implemented.'}
				return respond_dict(web, r500, dicty)
				
				wereDeleted = False # TODO: Set this to whether or not the results were actually deleted
				
				if wereDeleted == True:
					# Results were actually deleted - return 200 OK
					return respond_dict(web, r200, dicty)
				else:
					# Results weren't deleted - catostrophic failure, return r500
					dicty = {'reason': 'Sever error: Could not delete results for job ' + id + ' for unkown reasons.'}
					return respond_dict(web, r500, dicty)
		
		
### EXAMPLE CLASSES WHICH HANDLE XML PARSING ###

#class list_users:        
#    def GET(self):
#        output = 'users:[';
#        for child in root:
#                print('child', child.tag, child.attrib)
#                output += str(child.attrib) + ','
#        output += ']';
#        return output

#class get_user:
#    def GET(self, user):
#        for child in root:
#            if child.attrib['id'] == user:
#                return str(child.attrib)

# Main
if __name__ == '__main__':
	print ('Starting...')
	client = getClient()
	
#	pprint.pprint(client.describe_jobs(jobs=['410525a5-d67a-4606-afa4-570d97b3e9c4']))
#	print('\n')
#	pprint.pprint(client.describe_jobs(jobs=['410525a5-d67a-4606-afa4-570d97b3e9c4'])['jobs'][0]['status'])


	app.run()

'''
# Debug testing
	getResults('1')
	#areResultsThere('resultjson')
	client = getClient()
	print(dir(client))
	print('\n')
	
	print(json.dumps(client.list_jobs(jobQueue='queue')))
	
	print('\n')
	print('\n')
	print(client.list_jobs(jobQueue='queue'))
	print('\n')
	print(client.list_jobs(jobQueue='succeeded'))
	print('\n')
	print(client.list_jobs(jobQueue='failed'))
	print('\n')
	print(client.list_jobs(jobQueue='failedddd'))
	print('\n2')
	print(client.list_jobs(jobStatus='failed'))
	print('\n3')
	print(client.list_jobs(jobStatus='succeeded'))
	app.run()
	#web.httpserver.runsimple(app.wsgifunc(), ("127.0.0.1", 8080))
'''


'''
# Unusued mega-dictionary - doesn't work
bigdata = {
	
	'jobDefinitionName': 'compute',
	#'jobDefinitionArn': 'arn:aws:batch:us-east-1:500992819193:job-definition/compute:18',
	'jobDefinition': 'arn:aws:batch:us-east-1:500992819193:job-definition/compute:18',
	'revision': '18',
	'status': 'ACTIVE',
	'type': 'container',
	'parameters': '',
	'retryStrategy': json.dumps({
		'attempts': 1
	}),
	'containerProperties': json.dumps({
		'image': '500992819193.dkr.ecr.us-east-1.amazonaws.com/compute',
		'vcpus': 64,
		'memory': 450000,
		'command': [
			'myscript.sh',
			'60'
		],
		'jobRoleArn': 'arn:aws:iam::500992819193:role/batchrole',
		'volumes': [],
		'environment': [
			{
				'name': 'BATCH_FILE_S3_URL',
				'value': 's3://script-moliere/myscript.sh'
			},
			{
				'name': 'BATCH_FILE_TYPE',
				'value': 'script'
			},
			{
				'name': 'SOURCE_WORD',
				'value': word1
			},
			{
				'name': 'TARGET_WORD',
				'value': word2
			}
		],
		'mountPoints': [],
		'privileged': True,
		'ulimits': [],
		'user': 'root'
	})
};
'''


'''
#Unused, and doesn't work
def getResults(id):
	BUCKET_NAME = 'CSV_Results' # replace with your bucket name
	KEY = 'resultjson.txt' # replace with your object key

	s3 = boto3.resource('s3')

	try:
		bucket = s3.Bucket(BUCKET_NAME)
		
		print('\n\n' + str(bucket) + '\n')
		print(str(dir(bucket)) + '\n\n')
		
		print('@@')
		for key in bucket.objects.all():
			print(key)
		print('@@')
		
		res = bucket.download_file(KEY, id)
		
		print('>>>>>>>>>>>>>>>>>>>>>>>>>>>SUCCESS<<<<<<<<<<<<<<<<<<<<<<<')
	except botocore.exceptions.ClientError as e:
		print(e.response)
		if e.response['Error']['Code'] == "404":
			print(">>>>>>>>>>>>>>>>>>>The object does not exist.")
			return ''
		else:
			raise

#Unused, and doesn't work
def getResults2(id):
	s3 = boto3.resource('s3')
	
	copy_source = {
		'Bucket': 'mybucket',
		'Key': 'mykey'
	}
	
	bucket = s3.Bucket('otherbucket')
	bucket.copy(copy_source, 'otherkey')
'''