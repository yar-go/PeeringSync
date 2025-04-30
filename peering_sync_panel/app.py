import base64
import datetime
import io
import json
import os
import re
import time
import zipfile
from peering_sync_daemon import bencoder

from flask import Flask, request, render_template, redirect, url_for, send_file

from .daemonclient import DaemonSocketClient

app = Flask(__name__)



@app.route('/')
def index():
    all_info = daemon_window.send_command("GET_INFO")
    info = json.loads(all_info)

    if not info["networks"]:
        return render_template('empty.html', networks=None)

    networks = [(net['name'], net['identification_str']) for net in info["networks"]]
    return render_template('network_info.html', networks=networks,
                           network_id="1a0494323e066061b0bd583ce49544af23f7ce0632efc321dc3e1dd727a1d972")


@app.route("/<network_id>")
def network_info(network_id):
    all_info = daemon_window.send_command("GET_INFO")
    print(all_info)
    info = json.loads(all_info)
    networks = [(net['name'], net['identification_str']) for net in info["networks"]]
    if not info["networks"]:
        return redirect(url_for('index'))

    network = sorted(info['networks'], key=lambda a: a["identification_str"] == network_id)[0]
    statistic = network['statistic']
    statistic['loaded'] = format_size(statistic['total_size'] - statistic["left"]) + " ({0}%)".format(str(round((statistic['total_size'] - statistic["left"])/statistic['total_size']*100, ndigits=2)))
    statistic["total_size"] = format_size(statistic['total_size'])
    statistic["seed_ver"] =  str(datetime.datetime.utcfromtimestamp(statistic["seed_ver"]))
    statistic["uploaded_per_session"] = format_size(statistic["uploaded_per_session"])
    statistic["left"] = format_size(statistic["left"])
    statistic["file_path"] = os.path.abspath(statistic["file_path"])
    statistic["is_download"] = "Завантаження та відвантаження" if statistic["is_download"] else "Відвантаження"

    files = network['files']

    peers_map = bencoder.BenCoder.decode(base64.b64decode(network['map'].encode("utf-8")))
    nearest_peers = enumerate([bencoder.BenCoder.decode(i.encode()) for i in peers_map.keys()],1)

    # map
    nodes = list()
    nodes_labels = dict()
    edges = list()

    start_node = bencoder.BenCoder.encode([info["own_address"].split(":")[0], info["own_address"].split(":")[1],
                                           info["own_peer_id"]]).decode('utf-8')
    peers_map = {start_node:peers_map}

    print(peers_map)
    def walker(map):
        if not map: return
        for node in map.keys():
            master_addr, master_port, master_iden = bencoder.BenCoder.decode(node.encode())
            if not master_iden in nodes: nodes.append(master_iden)

            if info["own_peer_id"] == master_iden:
                nodes_labels[master_iden] = [f"(цей вузол)\\nАдреса:{master_addr}:{master_port}\\nID:{master_iden}",1]
            else:
                nodes_labels[master_iden] = [f"Адреса:{master_addr}:{master_port}\\nID:{master_iden}", 0]
            for child in map.get(node, {}).keys():
                child_addr, child_port, child_iden = bencoder.BenCoder.decode(child.encode())
                if not child_iden in nodes: nodes.append(child_iden)
                edges.append((master_iden, child_iden))
                if info["own_peer_id"] == child_iden:
                    nodes_labels[child_iden] = [f"(цей вузол)\\nАдреса:{child_addr}:{child_addr}\\nID:{child_addr}", 1]
                else:
                    nodes_labels[child_iden] = [f"Адреса:{child_addr}:{child_port}\\nID:{child_iden}", 0]
                walker(map.get(child, {}))

    walker(peers_map)

    return render_template('network_info.html', networks=networks,
                           network_id=network_id, statistic=statistic, own_address=info["own_address"],
                           own_peer_id=info["own_peer_id"], files=files, nearest_peers=nearest_peers,
                           nodes=nodes, edges=edges, nodes_labels=nodes_labels)


@app.route('/add_network', methods=['POST'])
def add_network():
    network_name = request.form.get('network_name')
    save_path = request.form.get('save_path')
    new_peers = request.form.get('peers_addresses')
    create_keys = request.form.get("create_new_keys")
    public_key = request.files.get('public_key')
    private_key = request.files.get('private_key')

    new_peers = [addr for addr in new_peers.split("\r\n") if validate_ipv4_port(addr)]
    new_peers = ','.join(new_peers)
    if create_keys:
        command = f"create_network~{network_name}~{save_path}"
    else:
        pub_key = public_key.stream.read()
        priv_key = private_key.stream.read()
        keys = pub_key.decode() + "\n\n\n" + priv_key.decode()
        command = f"import_network~{network_name}~{keys}~{save_path}"

    if new_peers: command += f"~{new_peers}"
    new_network_id = daemon_window.send_command(command)

    return redirect(url_for("network_info", network_id=new_network_id))


@app.route('/delete_network', methods=['POST'])
def delete_network():
    network_id = request.form.get("network_id")
    command = f"delete_network~{network_id}"
    daemon_window.send_command(command)
    return redirect(url_for("index"))


@app.route('/export_network', methods=['POST'])
def export_network():
    network_id = request.form.get("network_id")
    command = f"export_network~{network_id}"
    res = daemon_window.send_command(command)

    ks = res.rsplit("\n\n\n")
    public = ks[0]
    if len(ks)>1:
        private = ks[1]
    else: private = None

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("public.pem", public)
        if private:
            zip_file.writestr("private.pem", private)
    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{network_id}.zip'
    )



@app.route('/add_peers', methods=['POST'])
def add_peers():
    peers_addresses = request.form.get('peers_addresses')
    network_id = request.form.get("network_id")
    new_peers = [addr for addr in peers_addresses.split("\r\n") if validate_ipv4_port(addr)]
    new_peers = ','.join(new_peers)
    command = f"ADD_PEERS~{network_id}~{new_peers}"
    daemon_window.send_command(command)
    time.sleep(1.1)
    return redirect(url_for("network_info", network_id=network_id))



@app.route('/update_files', methods=['POST'])
def update_files():
    network_id = request.form.get("network_id")
    command = f"update_files~{network_id}"
    daemon_window.send_command(command)
    return redirect(url_for("network_info", network_id=network_id))


@app.route("/open_folder", methods=["POST"])
def open_folder():
    network_id = request.form.get("network_id")
    command = f"open_folder~{network_id}"
    daemon_window.send_command(command)
    return redirect(url_for("network_info", network_id=network_id))


def validate_ipv4_port(input_string):
    ipv4_port_pattern = r'^((\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})):(\d{1,5})$'
    match = re.match(ipv4_port_pattern, input_string)
    if not match:
        return False
    for i in range(1, 5):
        octet = int(match.group(i + 1))
        if octet < 0 or octet > 255:
            return False
    port = int(match.group(6))
    if port < 1 or port > 65535:
        return False
    return True


def format_size(bytes_size):
    # Перевірка на правильність введених даних
    if bytes_size < 0:
        raise ValueError("Розмір у байтах не може бути від'ємним.")

    units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
    index = 0

    while bytes_size >= 1024 and index < len(units) - 1:
        bytes_size /= 1024
        index += 1

    return f"{bytes_size:.2f} {units[index]}"


def run_app(port, sock_path):
    global daemon_window
    daemon_window = DaemonSocketClient(sock_path)
    app.run(port=port)
