from flask_cors import CORS
from datetime import timedelta
from flask import Flask, render_template, request, jsonify, make_response
import argparse
from tqdm import trange
import requests
import os
import sys
import csv
import pandas as pd
from time import sleep
from datetime import datetime

# URLs to make api calls
BASE_URL = "https://metamon-api.radiocaca.com/usm-api"
TOKEN_URL = f"{BASE_URL}/login"
LIST_MONSTER_URL = f"{BASE_URL}/getWalletPropertyBySymbol"
CHANGE_FIGHTER_URL = f"{BASE_URL}/isFightMonster"
START_FIGHT_URL = f"{BASE_URL}/startBattle"
LIST_BATTLER_URL = f"{BASE_URL}/getBattelObjects"
WALLET_PROPERTY_LIST = f"{BASE_URL}/getWalletPropertyList"
LVL_UP_URL = f"{BASE_URL}/updateMonster"
MINT_EGG_URL = f"{BASE_URL}/composeMonsterEgg"

server = Flask(__name__)

cors = CORS(server, resources={r"/v2/service/*": {"origins": "*"}})
server.config['CORS_HEADERS'] = 'Content-Type'
server.secret_key = 'AutoverseSecretkey123!@#'
server.config['SESSION_TYPE'] = 'filesystem'
server.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=60)
server.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024


def datetime_now():
    return datetime.now().strftime("%m/%d/%Y %H:%M:%S")


def post_formdata(payload, url="", headers=None):
    """Method to send request to game"""
    files = []
    if headers is None:
        headers = {}

    # Add delay to avoid error from too many requests per second
    sleep(0.5)

    for _ in range(5):
        try:
            response = requests.request("POST",
                                        url,
                                        headers=headers,
                                        data=payload,
                                        files=files)
            return response.json()
        except:
            continue
    return {}


def get_battler_score(monster):
    """ Get opponent's power score"""
    return monster["sca"]


def picker_battler(monsters_list):
    """ Picking opponent """
    battlers = list(filter(lambda m: m["rarity"] == "N", monsters_list))

    if len(battlers) == 0:
        battlers = list(filter(lambda m: m["rarity"] == "R", monsters_list))

    battler = battlers[0]
    score_min = get_battler_score(battler)
    for i in range(1, len(battlers)):
        score = get_battler_score(battlers[i])
        if score < score_min:
            battler = battlers[i]
            score_min = score
    return battler


def pick_battle_level(level=1):
    # pick highest league for given level
    if 21 <= level <= 40:
        return 2
    if 41 <= level <= 60:
        return 3
    return 1


class MetamonPlayer:

    def __init__(self,
                 address,
                 sign,
                 msg="LogIn",
                 auto_lvl_up=False,
                 output_stats=False):
        self.no_enough_money = False
        self.output_stats = output_stats
        self.total_bp_num = 0
        self.total_success = 0
        self.total_fail = 0
        self.mtm_stats_df = []
        self.token = None
        self.address = address
        self.sign = sign
        self.msg = msg
        self.auto_lvl_up = auto_lvl_up

    def init_token(self):
        """Obtain token for game session to perform battles and other actions"""
        payload = {"address": self.address, "sign": self.sign, "msg": self.msg}
        response = post_formdata(payload, TOKEN_URL)
        self.token = response.get("data")

    def change_fighter(self, monster_id):
        """Switch to next metamon if you have few"""
        payload = {
            "metamonId": monster_id,
            "address": self.address,
        }
        post_formdata(payload, CHANGE_FIGHTER_URL)

    def list_battlers(self, monster_id, front=1):
        """Obtain list of opponents"""
        payload = {
            "address": self.address,
            "metamonId": monster_id,
            "front": front,
        }
        headers = {
            "accessToken": self.token,
        }
        response = post_formdata(payload, LIST_BATTLER_URL, headers)
        return response.get("data", {}).get("objects")

    def start_fight(self,
                    my_monster,
                    target_monster_id,
                    loop_count=1):
        """ Main method to initiate battles (as many as monster has energy for)"""
        success = 0
        fail = 0
        total_bp_fragment_num = 0
        mtm_stats = []
        my_monster_id = my_monster.get("id")
        my_monster_token_id = my_monster.get("tokenId")
        my_level = my_monster.get("level")
        my_power = my_monster.get("sca")
        battle_level = pick_battle_level(my_level)

        tbar = trange(loop_count)
        tbar.set_description("Fighting...")
        for _ in tbar:
            payload = {
                "monsterA": my_monster_id,
                "monsterB": target_monster_id,
                "address": self.address,
                "battleLevel": battle_level,
            }
            headers = {
                "accessToken": self.token,
            }
            response = post_formdata(payload, START_FIGHT_URL, headers)
            code = response.get("code")
            if code == "BATTLE_NOPAY":
                self.no_enough_money = True
                break
            data = response.get("data", {})
            fight_result = data.get("challengeResult", False)
            bp_fragment_num = data.get("bpFragmentNum", 10)

            if self.auto_lvl_up:
                # Try to lvl up
                res = post_formdata({"nftId": my_monster_id, "address": self.address},
                                    LVL_UP_URL,
                                    headers)
                code = res.get("code")
                if code == "SUCCESS":
                    tbar.set_description(
                        "LVL UP successful! Continue fighting...")
                    my_level += 1
                    # Update league level if new level is 21 or 41
                    battle_level = pick_battle_level(my_level)

            self.total_bp_num += bp_fragment_num
            total_bp_fragment_num += bp_fragment_num
            if fight_result:
                success += 1
                self.total_success += 1
            else:
                fail += 1
                self.total_fail += 1

        mtm_stats.append({
            "My metamon id": my_monster_token_id,
            "League lvl": battle_level,
            "Total battles": loop_count,
            "My metamon power": my_power,
            "My metamon level": my_level,
            "Victories": success,
            "Defeats": fail,
            "Total egg shards": total_bp_fragment_num,
            "Timestamp": datetime_now()
        })

        mtm_stats_df = pd.DataFrame(mtm_stats)
        print(mtm_stats_df)
        self.mtm_stats_df.append(mtm_stats_df)

    def get_wallet_properties(self):
        """ Obtain list of metamons on the wallet"""
        data = []
        page = 1
        while True:
            payload = {"address": self.address, "page": page, "pageSize": 60}
            headers = {
                "accessToken": self.token,
            }
            response = post_formdata(payload, WALLET_PROPERTY_LIST, headers)
            mtms = response.get("data", {}).get("metamonList", [])
            if len(mtms) > 0:
                data.extend(mtms)
                page += 1
            else:
                break
        return data

    def list_monsters(self):
        """ Obtain list of metamons on the wallet (deprecated)"""
        payload = {"address": self.address,
                   "page": 1, "pageSize": 60, "payType": -6}
        headers = {"accessToken": self.token}
        response = post_formdata(payload, LIST_MONSTER_URL, headers)
        monsters = response.get("data", {}).get("data", {})
        return monsters

    def battle(self, w_name=None):
        """ Main method to run all battles for the day"""
        resultText = "";
        if w_name is None:
            w_name = self.address

        summary_file_name = f"{w_name}_summary.tsv"
        mtm_stats_file_name = f"{w_name}_stats.tsv"
        self.init_token()

        self.get_wallet_properties()
        monsters = self.list_monsters()
        wallet_monsters = self.get_wallet_properties()
        print(f"Monsters total: {len(wallet_monsters)}")
        resultText += f"Monsters total: {len(wallet_monsters)}"

        available_monsters = [
            monster for monster in wallet_monsters if monster.get("tear") > 0
        ]
        stats_l = []
        print(f"Available Monsters : {len(available_monsters)}")
        resultText += f"\nAvailable Monsters : {len(available_monsters)}\n"
        for monster in available_monsters:
            monster_id = monster.get("id")
            tear = monster.get("tear")
            level = monster.get("level")
            battlers = self.list_battlers(monster_id)
            battler = picker_battler(battlers)
            target_monster_id = battler.get("id")

            self.change_fighter(monster_id)

            self.start_fight(monster,
                             target_monster_id,
                             loop_count=tear)
            if self.no_enough_money:
                print("Not enough u-RACA")
                resultText += "Not enough u-RACA\n"
                break
        total_count = self.total_success + self.total_fail
        success_percent = .0
        if total_count > 0:
            success_percent = (self.total_success / total_count) * 100

        if total_count <= 0:
            print("No battles to record")
            resultText += "No battles to record\n"
            return resultText

        stats_l.append({
            "Victories": self.total_success,
            "Defeats": self.total_fail,
            "Win Rate": f"{success_percent:.2f}%",
            "Total Egg Shards": self.total_bp_num,
            "Datetime": datetime_now()
        })
        resultText += f"\nVictories: {self.total_success}\n"
        resultText += f"Defeats: {self.total_fail}\n"
        resultText += f"Win Rate: {success_percent:.2f}%\n"
        resultText += f"Total Egg Shards: {self.total_bp_num}\n"

        stats_df = pd.DataFrame(stats_l)
        print(stats_df)
        if os.path.exists(summary_file_name) and self.output_stats:
            back_fn = f"{summary_file_name}.bak"
            os.rename(summary_file_name, back_fn)
            tmp_df = pd.read_csv(back_fn, sep="\t", dtype="str")
            stats_upd_df = pd.concat([stats_df, tmp_df])
            stats_df = stats_upd_df
            os.remove(back_fn)

        if self.output_stats:
            stats_df.to_csv(summary_file_name, index=False, sep="\t")

        mtm_stats_df = pd.concat(self.mtm_stats_df)
        if os.path.exists(mtm_stats_file_name) and self.output_stats:
            back_fn = f"{mtm_stats_file_name}.bak"
            os.rename(mtm_stats_file_name, back_fn)
            tmp_df = pd.read_csv(back_fn, sep="\t", dtype="str")
            upd_df = pd.concat([mtm_stats_df, tmp_df])
            mtm_stats_df = upd_df
            os.remove(back_fn)
        if self.output_stats:
            mtm_stats_df.to_csv(mtm_stats_file_name, sep="\t", index=False)
        return resultText

    def mint_eggs(self):
        self.init_token()

        headers = {
            "accessToken": self.token,
        }
        payload = {"address": self.address}

        minted_eggs = 0

        while True:
            res = post_formdata(payload, MINT_EGG_URL, headers)
            code = res.get("code")
            if code != "SUCCESS":
                break
            minted_eggs += 1
        print(f"Minted Eggs Total: {minted_eggs}")
        return f"Minted Eggs Total: {minted_eggs}\n"


def _build_cors_preflight_response():
    response = make_response()
    response.headers.add('Access-Control-Allow-Headers', "*")
    response.headers.add('Access-Control-Allow-Methods', "*")
    response.headers.add('Access-Control-Allow-Credentials', "true")
    return response


def _corsify_actual_response(response):
    return response


@server.route('/')
def index():
    return render_template("index.html")


@server.route('/auto/metamon/', methods=['POST', 'OPTIONS'])
def auto_metamon():
    if request.method == "OPTIONS":  # CORS preflight
        return _build_cors_preflight_response()
    elif request.method == "POST":
        content = request.get_json()
        name = content['name']
        address = content['address']
        sign = content['sign']
        msg = content['msg']
        autoLevel = content['autoLevel']
        autoMintEgg = content['autoMintEgg']
        skipBattles = content['skipBattles']
        finalLog = ""

        mtm = MetamonPlayer(address=address,
                                sign=sign,
                                msg=msg,
                                auto_lvl_up=autoLevel,
                                output_stats=False)
        if not skipBattles:
            finalLog = mtm.battle(w_name=name)
        if autoMintEgg:
            finalLog += mtm.mint_eggs()
        return _corsify_actual_response(jsonify({"status": "success", "msg": finalLog}))


if __name__ == '__main__':
    server.run(host='0.0.0.0', port=8080, debug=True)