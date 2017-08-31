import os,errno
import ConfigParser
import pymysql.cursors
from dulwich.repo import Repo as git_repo
import click

def load_repo(repo_path):
  """
  Load git repository at the given path, initializing if necessary.

  Inputs:
    * repo_path (str): a path to the output repository
  Output:
    * repo (dulwich.repo.Repo): the git repository
  """
  try:
    os.mkdir(repo_path)
  except OSError as e:
    if e.errno == errno.EEXIST:
      pass
    else:
      raise e
  try:
    repo = git_repo.init(repo_path)
  except OSError as e:
    if e.errno == errno.EEXIST:
      repo = git_repo(repo_path)
    else:
      raise e
  return repo

def load_new_revisions(db_config, web_id, latest_revision_id=0):
  """
  Load all revisions, using the given database configuration to connect.  If a
  `latest_revision_id` is provided, only loads revisions committed after that.
  """
  db_conn = pymysql.connect(host=db_config["host"],
                            user=db_config["user"],
                            password=db_config["password"],
                            db=db_config["db"],
                            charset=db_config["charset"],
                            cursorclass=pymysql.cursors.DictCursor)
  try:
    with db_conn.cursor() as cursor:
      query = ("SELECT r.id,r.page_id,r.author,r.ip,r.revised_at,r.content,p.name"
        " FROM revisions r INNER JOIN pages p ON (r.page_id=p.id)"
        " WHERE r.web_id=%s AND r.id>%s"
        " ORDER BY r.id") % (web_id, latest_revision_id)
      cursor.execute(query)
      revisions = cursor.fetchall()
  finally:
    db_conn.close()
  return revisions

def commit_revisions_to_repo(repo, revisions):
  """
  Commits a set of revisions to the given git repository.

  Inputs:
    * repo (dulwich.repo.Repo): the git repository
    * revisions ([dict]): the revisions, as a list of dictionaries
  Output:
    * latest_revision_id (str): the latest revision id that was committed
  """
  latest_revision_id = None
  for rev in revisions:
    with open("%s/%s" % (repo.path, rev["page_id"]), "wb") as f:
      f.write(bytes(rev["content"], "utf8"))
    repo.stage([bytes("%d" % rev["page_id"], "utf8")])
    commit_msg = """Revision ID: %s
Revision date: %s
Page name: %s
Author: %s
IP address: %s""" % (rev["id"], rev["revised_at"], rev["name"], rev["author"],
      rev["ip"])
    commit_author = "%s <>" % rev["author"]
    
    repo.do_commit(bytes(commit_msg, "utf8"), bytes(commit_author, "utf8"))
    latest_revision_id = rev["id"]
  return latest_revision_id

def load_and_commit_new_revisions(repo_path, db_config, web_id,
  latest_revision_id=0):
  repo = load_repo(repo_path)
  revs = load_new_revisions(db_config, web_id, latest_revision_id)
  latest_revision_id = commit_revisions_to_repo(repo, revs)
  return latest_revision_id

@click.command()
@click.option("--config-file",
  type=click.Path(exists=True),
  default=os.path.expanduser("~/.instiki2git"),
  help="Path to configuration file.")
@click.option("--latest-revision-file",
  type=click.Path(),
  default="/tmp/instiki2git",
  help="Path to a file containing the ID of the last committed revision.")
def cli(config_file, latest_revision_file):
  config_parser = ConfigParser.RawConfigParser()
  config_parser.read(config_file)
  repo_path = config_parser.get("repository", "path")
  db_config = {"host": config_parser.get("database", "host"),
    "db": config_parser.get("database", "db"),
    "user": config_parser.get("database", "user"),
    "password": config_parser.get("database", "password"),
    "charset": config_parser.get("database", "charset")}
  web_id = config_parser.get("web", "id")
  if os.path.exists(latest_revision_file):
    with click.open_file(latest_revision_file, "rw") as f:
      try:
        latest_revision_id = int(f.read())
      except ValueError:
        latest_revision_id = 0
      latest_revision_id = load_and_commit_new_revisions(repo_path, db_config,
        web_id, latest_revision_id)
      f.write(str(latest_revision_id))
  else:
    latest_revision_id = 0
    latest_revision_id = load_and_commit_new_revisions(repo_path, db_config,
        web_id, latest_revision_id)
    with click.open_file(latest_revision_file, "w+") as f:
      f.write(str(latest_revision_id))
