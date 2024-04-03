from asyncio.windows_events import NULL
from pickle import FALSE
from flask import Flask, render_template, request, url_for
import psycopg2
from psycopg2 import sql
from pathlib import Path
import requests
import xml.etree.ElementTree as ET
from tkinter import messagebox
from pyquery import PyQuery as pq
from lxml import objectify
import lxml.etree
import time


app = Flask(__name__)

db_Conf_Params = {
     'host':'',
     'port': '',
     'database': '',
     'user': '',
     'password': ''
}

@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html',db_Conf_Params= db_Conf_Params)

@app.route('/deleteRecordsAndReworkProject', methods=['POST'])
def deleteRecordsAndReworkProject():
    try:
        db_host = request.form.get('db_host')
        db_port = request.form.get('db_port')
        db_name = request.form.get('db_name')
        db_user = request.form.get('db_user')
        db_password = request.form.get('db_password')
        if db_host and db_port and db_name and db_user and db_password:
            db_params = {
                'host': db_host,
                'port': db_port,
                'database': db_name,
                'user': db_user,
                'password': db_password
            }
            connection = psycopg2.connect(**db_params)
            if connection:
             connection.close()
            return render_template('deleteAndRework.html',db_params= db_params,db_host=db_host)
    except psycopg2.Error as e:
            return render_template('index.html',db_Conf_Params= '') 


@app.route('/deleteRecord', methods=['GET', 'POST'])
def deleteRecord():
    projectId = request.form.get('project_id')
    gtSpec = request.form.get('gt_list')
    if delete_records(projectId,gtSpec,db_Conf_Params) == True:
        return render_template('deleteAndRework.html',db_params= db_Conf_Params,errorMsg='',successMsg = "Record For GT :'{spec}' at {id} Was Deleted Successfully".format(spec=gtSpec,id = projectId))
    else:
        return render_template('deleteAndRework.html',db_params= db_Conf_Params,errorMsg = "Deleeting Records Was Failed")

def delete_records(project_id,gtSpec, db_params):
    try:
        connection = psycopg2.connect(**db_params)
        cursor = connection.cursor()

        queries = [
            """
            DELETE FROM guidedtaskdb.gt_project
            WHERE project_id = %s
            """,
            """
            DELETE FROM guidedtaskdb.gt_validator
            USING guidedtaskdb.gt_control gc
            JOIN guidedtaskdb.gt_control_group gcp ON gc.group_id = gcp.id
            JOIN guidedtaskdb.gt_page gp ON gcp.page_id = gp.id
            JOIN guidedtaskdb.gt g ON gp.task_id = g.id
            WHERE gt_validator.control_id = gc.id
              AND g.project_id = %s
            """,
            """
            DELETE FROM guidedtaskdb.gt_control
            USING guidedtaskdb.gt_control_group gcp
            JOIN guidedtaskdb.gt_page gp ON gcp.page_id = gp.id
            JOIN guidedtaskdb.gt g ON gp.task_id = g.id
            WHERE guidedtaskdb.gt_control.group_id = gcp.id
              AND g.project_id = %s
            """,
            """
            DELETE FROM guidedtaskdb.gt_control_group gcp
            USING guidedtaskdb.gt_page gp
            JOIN guidedtaskdb.gt g ON gp.task_id = g.id
            WHERE gcp.page_id = gp.id
              AND g.project_id = %s
            """,
            """
            DELETE FROM guidedtaskdb.gt_layout gl
            USING guidedtaskdb.gt_page gp
            JOIN guidedtaskdb.gt g ON gp.task_id = g.id
            WHERE gl.page_id = gp.id
              AND g.project_id = %s
            """,
            """
            DELETE FROM guidedtaskdb.gt_page gp
            USING guidedtaskdb.gt g
            WHERE gp.task_id = g.id
              AND g.project_id = %s
            """,
            """
            DELETE FROM guidedtaskdb.gt gts
            WHERE gts.project_id = %s
                AND gts.task_type ='{spec}'
            """.format(spec = gtSpec)
        ]
        gts = getProjectGts(project_id,db_params)   
        if gts:
            for query in queries:
                print(f"Executing query: {query}")
                cursor.execute(sql.SQL(query), (project_id,))
                connection.commit()

            print("Deletion completed successfully.")
            if connection:
                connection.close()
            return True
        else:
            return False
    except psycopg2.Error as e:
        print(f"Error: {e}")
        return False
    
def getProjectGts(project_id, db_params):
    try:
        connection = psycopg2.connect(**db_params)
        cursor = connection.cursor()
        query = "SELECT * FROM guidedtaskdb.gt where gt.project_id like '"+project_id+"'"
        cursor.execute(query)
        data = cursor.fetchall()
        connection.commit()
        return data
    
    except psycopg2.Error as e:
        print(f"Error: {e}")
    finally:
        if connection:
            connection.close()
     
@app.route('/getGts', methods=['POST'])
def getGts():
    projectId = request.form['id']
    gts = getProjectGts(projectId,db_Conf_Params)
    result = []
    for item in gts:
        result.append(item[8])
    return list(set(result))

@app.route('/reworkProject', methods=['POST'])
def reworkProject():
    nodeIp = db_Conf_Params['host']
    projectId = request.form.get('project_id')
    reason = request.form.get('reason')
    comments = request.form.get('comments')
    token = login(nodeIp)
    if token == None:
        return render_template('deleteAndRework.html',db_params= db_Conf_Params,successMsgRework='',errMsgRework="ConnectionError:Cannot get token from this ip: {nodeIp}".format(nodeIp=nodeIp))
    else:
        response = rework(nodeIp,token,projectId,reason,comments)
        if(response!=None and response.status_code == 200):
            return render_template('deleteAndRework.html',db_params= db_Conf_Params,successMsgRework = "Reowrk For Reason: '{res}' at {id} Was Execucted Successfully".format(res=reason,id=projectId))
        else:
            return render_template('deleteAndRework.html',db_params= db_Conf_Params,successMsgRework='',errMsgRework="Reowrk For Reason: '{res}' at {id} Was Failed".format(res=reason,id=projectId))

def rework(node_ip , token , project_id , reason , comments):
    try:
        url = "https://{env}/aff/ProjectStoreSvc".format(env = node_ip)
        with open('rework-request-sample.conf') as f:
              request = f.read().replace('\n', '')
        request = request.replace("reworkProjectRequestToken",token)
        request = request.replace("reworkProjectRequestProjectId",project_id)
        request = request.replace("reworkProjectRequestReasonCode",reason)
        request = request.replace("reworkProjectRequestReasonComments",comments)
        response = requests.post(url, data=request,headers={"Content-Type": "application/xml"},verify=False)
        return response
    except Exception as e:
        print(f"Error: {e}")


def login(node_ip):
    try:
        url = "http://{env}/dop/security/rest/loginservice/login".format(env = node_ip)
        response = requests.post(url,json={"userID":"AFFSuper","password":"AFFSuper123"},verify=False)
        return response.text
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    with open('configurations.conf') as f:
          lines = f.readlines()  
    if lines:
        for line in lines:
            line = line.strip().split(":")
            key = line[0]
            val = line[1]
            db_Conf_Params[key] = val
    else:
        db_Conf_Params = ''
    app.run(debug=True)
    