
import asana
import json
import os

from github import Github

class SyncerTask(object):

	fields : str = "name,resource_type,notes,permalink_url,completed"

	def __init__(self,data:dict):
		self.id : str = data["gid"]
		self.name : str = data["name"]
		self.notes : str = data["notes"]
		self.link : str = data["permalink_url"]
		self.completed : bool = data["completed"]

class SyncerConfig(object):

	def __init__(self):
		if not os.path.exists("config.json"):
			exit("ERROR: Failed to load config.json - You need a config to be able to run sync.")
		f = open("config.json")
		d = json.loads(f.read())
		f.close()

		asana : dict = d["asana"]
		self.asana_access_token : str = asana["access_token"]
		self.desired_projects : list[str] = asana["desired_projects"]
		self.workspace_name : str = asana["workspace_name"]
		
		github : dict = d["github"]
		self.github_access_token : str = github["access_token"]

class SyncerProject(object):

	def __init__(self):
		self.id : str = None
		self.name : str = None
		self.backlog_id :str = None
		self.tasks : list[SyncerTask]= []
	
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
		self.workspace_id : str = None
		self.projects : list[SyncerProject] = []
	
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
		f.write(json.dumps(self.data,indent="\t"))
		f.close()

	def load(self):
		if os.path.exists("state.db"):			
			f = open("state.db")
			data = json.loads(f.read())
			self.from_data(data)
			f.close()

class Syncer(object):

	def __init__(self,config:SyncerConfig):
		self.config : SyncerConfig = config
		self.asana = asana.Client.access_token(config.asana_access_token)
		self.github = Github(config.github_access_token)
		self.state : SyncerState = SyncerState()

	def load_workspace(self):
		me = self.asana.users.me()
		print("Hello " + me['name'])
		
		print("Loading asana workspaces...")
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

		result = self.asana.projects.get_projects_for_workspace(self.state.workspace_id, opt_pretty=True)

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
		print(f"Loading asana backlog for project {project.name}...")

		result = self.asana.sections.get_sections_for_project(project.id, opt_pretty=True)
		
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
		print(f"Checking asana backlog for project {project.name}...")
		result = self.asana.tasks.get_tasks_for_section(project.backlog_id, opt_pretty=True,opt_fields=SyncerTask.fields)
		for r in result:			
			rtype = r["resource_type"]
			if rtype == "task":
				task = SyncerTask(data=r)
				project.tasks.append(task)
				print(f"> Found {task.id}:{task.name}")
				print(r)

config = SyncerConfig()
syncer = Syncer(config=config)
syncer.setup()

for project in syncer.state.projects:
	syncer.check(project)
