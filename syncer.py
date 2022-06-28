
import asana
import json
import os


# Access token obtained here - https://app.asana.com/0/developer-console

class Task(object):

	def __init__(self,id:str,name:str):
		self.id = id
		self.name = name

class SyncerConfig(object):

	def __init__(self):
		if not os.path.exists("config.json"):
			exit("ERROR: Failed to load config.json - You need a config to be able to run sync.")
		f = open("config.json")
		d = json.loads(f.read())
		f.close()
		self.access_token = d["access_token"]
		self.desired_projects = d["desired_projects"]
		self.workspace_name = d["workspace_name"]

class SyncerProject(object):

	def __init__(self):
		self.id = None
		self.name = None
		self.backlog_id = None
		self.tasks = []
	
	def from_data(self,data:dict):
		self.id = data.get("id")
		self.name = data.get("name")
		self.backlog_id = data.get("backlog_id")

	@property
	def data(self):
		return {
			"id":self.id,
			"name":self.name,
			"backlog_id":self.backlog_id,
		}

class SyncerState(object):

	def __init__(self):
		self.workspace_id = None
		self.projects = []
	
	def from_data(self,data:dict):
		self.workspace_id = data.get("workspace_id")
		projects = data.get("projects")
		for proj_data in projects:
			proj = SyncerProject()
			proj.from_data(proj_data)
			self.projects.append(proj)

	@property
	def data(self):
		projects = []
		for project in self.projects:
			projects.append(project.data)
		return {
			"workspace_id":self.workspace_id,
			"projects":projects,
		}

	def save(self):
		f = open("state.db","w")
		f.write(json.dumps(self.data))
		f.close()

	def load(self):
		if os.path.exists("state.db"):			
			f = open("state.db")
			data = json.loads(f.read())
			self.from_data(data)
			f.close()

class Syncer(object):

	def __init__(self,config:SyncerConfig):
		self.config = config
		self.client = asana.Client.access_token(config.access_token)		
		self.state = SyncerState()

	def load_workspace(self):
		me = self.client.users.me()
		print("Hello " + me['name'])
		
		print("Loading workspaces...")
		workspaces = me['workspaces']
		workspace_id = None

		for ws in workspaces:
			if ws["name"] != self.config.workspace_name:
				continue
			workspace_id = ws["gid"]
		
		if workspace_id is None:
			exit(f"Failed to locate {self.config.workspace_name} workspace")

		self.state.workspace_id = workspace_id
		self.state.save()

	def load_desired_projects(self):
		print("Loading desired projects...")
		projects = []

		result = self.client.projects.get_projects_for_workspace(self.state.workspace_id, opt_pretty=True)

		counter = 0
		for r in result:
			if r["name"] in self.config.desired_projects:
				project = SyncerProject()
				project.name = r["name"]
				project.id = r["gid"]
				projects.append(project)
			counter += 1

		print(f"Found {len(projects)} desired projects out of {counter} projects")
		
		if len(projects) == 0:
			exit("Failed to locate desired projects")

		self.state.projects = projects
		self.state.save()				

	def load_backlog_for_project(self,project:SyncerProject):
		print(f"Loading backlog for project {project.name}...")

		result = self.client.sections.get_sections_for_project(project.id, opt_pretty=True)
		
		backlog_id = None
		for section in result:
			if section["name"] == "Backlog":
				backlog_id = section["gid"]
		
		if backlog_id is None:
			exit(f"Failed to locate backlog for {project.name}")
		
		project.backlog_id = backlog_id
		self.state.save()

	def setup(self):
		
		self.state.load()
		
		reloaded = False
		if self.state.workspace_id is None:
			self.load_workspace()
			reloaded = True

		if len(self.config.desired_projects) != len(self.state.projects):
			self.load_desired_projects()
			reloaded = True
		
		for project in self.state.projects:
			if project.backlog_id is None:
				self.load_backlog_for_project(project)

		if reloaded:
			print(f"Setup successfully with {len(self.state.projects)} projects")
		else:
			print(f"Setup loaded from stored state successfully with {len(self.state.projects)} projects")

	def check(self,project:SyncerProject):
		print(f"Checking backlog for project {project.name}...")
		result = self.client.tasks.get_tasks_for_section(project.backlog_id, opt_pretty=True)		
		for r in result:			
			rtype = r["resource_type"]
			if rtype == "task":
				task = Task(id=r["gid"],name=r["name"])
				project.tasks.append(task)
				print(f"> Found {task.id}:{task.name}")

config = SyncerConfig()
syncer = Syncer(config=config)
syncer.setup()

for project in syncer.state.projects:
	syncer.check(project)
