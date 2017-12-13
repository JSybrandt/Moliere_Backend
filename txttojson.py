import sys

infile = open(sys.argv[1], 'r')
outfile = open(sys.argv[2], 'w')

outfile.write("[\n")
obj = ""

for line in infile:
	if (line.startswith("TOPIC")):
		obj = "\t{\n\t\t\"TopicVal\": \"" + line[line.rfind(' ')+1:-1] + "\",\n"
		obj += "\t\t\"Keywords\": [\n"
		infile.next()
	elif (len(line)>1):
		obj+= "\t\t\t{\"" + line[0:line.find(' ')] + "\": " + line[line.rfind(' ')+1:-1] + "},\n"
	elif (obj != ""):
		obj = obj[:-2]
		obj += "\n\t\t]\n\t}\n"
		outfile.write(obj)
obj= obj[:-2]
obj += "\n\t\t]\n\t}\n]"
outfile.write(obj)
