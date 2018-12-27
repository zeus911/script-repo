#!/usr/local/bin/python3

import sys
import urllib.request
import urllib.parse
import http.cookiejar
import requests
import json
from datetime import datetime


class AlarmHandler:

    def __init__(self,
                 weixin_user_id,
                 zabbix_alarm_subject,
                 zabbix_alarm_message,
                 zabbix_username,
                 zabbix_password,
                 zabbix_login_url,
                 zabbix_get_picture_url
                 ):

        self.WEIXIN_USER_ID = weixin_user_id
        self.WEIXIN_CORP_ID = 'wxd************28e'
        self.WEIXIN_SECRET = 'TLj*************************************DnE'
        self.WEIXIN_APP_ID = 111

        self.GET_WEIXIN_ACCESS_TOKEN_URL = \
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORPID}&corpsecret={SECRET}".format(
                CORPID=self.WEIXIN_CORP_ID, SECRET=self.WEIXIN_SECRET)

        response_context = json.loads(urllib.request.urlopen(
            self.GET_WEIXIN_ACCESS_TOKEN_URL).read().decode('utf-8'))
        self.WEIXIN_ACCESS_TOKEN = response_context['access_token']

        self.WEIXIN_SEND_MESSAGE_URL = \
            "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={ACCESS_TOKEN}".format(
                ACCESS_TOKEN=self.WEIXIN_ACCESS_TOKEN)

        self.WEIXIN_UPLOAD_PICTURE_URL = \
            "https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={ACCESS_TOKEN}&type=image".format(
                ACCESS_TOKEN=self.WEIXIN_ACCESS_TOKEN)

        self.ZABBIX_ALARM_SUBJECT = zabbix_alarm_subject
        self.ZABBIX_ALARM_MESSAGE = json.loads(zabbix_alarm_message)
        self.ZABBIX_USERNAME = zabbix_username
        self.ZABBIX_PASSWORD = zabbix_password
        self.ZABBIX_LOGIN_URL = zabbix_login_url
        self.ZABBIX_GET_PICTURE_URL = zabbix_get_picture_url

        # 创建cookie用于登录
        cookie_jar = http.cookiejar.CookieJar()
        url_opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookie_jar))

        values = {
            'name': self.ZABBIX_USERNAME,
            'password': self.ZABBIX_PASSWORD,
            'autologin': 1,
            "enter": 'Sign in'
        }

        data = urllib.parse.urlencode(values).encode(encoding='UTF8')
        request = urllib.request.Request(self.ZABBIX_LOGIN_URL, data)
        url_opener.open(request, timeout=10)

        # 保存url_opener
        self.urlOpener = url_opener

    def get_picture(self,
                    picture_save_path,
                    picture_file_name,
                    picture_height=100,
                    picture_width=450,
                    picture_period=3600):

        zabbix_item_id = self.ZABBIX_ALARM_MESSAGE['itemid']
        zabbix_picture_path = picture_save_path + picture_file_name

        values = {
            'itemids[]': zabbix_item_id,
            'height': picture_height,
            'width': picture_width,
            'period': picture_period,
            # 获取当前时间，监控图截取到当前时间
            'stime': datetime.now().strftime('%Y%m%d%H%M%S'),
        }

        data = urllib.parse.urlencode(values).encode(encoding='UTF8')
        request = urllib.request.Request(self.ZABBIX_GET_PICTURE_URL, data)
        url = self.urlOpener.open(request)

        # 下载监控图，写入文件
        with open(zabbix_picture_path, 'wb') as picture_file:
            picture = url.read()
            picture_file.write(picture)

        return zabbix_picture_path

    def upload_picture_to_weixin(self, upload_picture_path):

        filename = datetime.now().strftime('%Y%m%d%H%M%S') + '.jpg'

        files = {
            'media': (
                filename,
                open(upload_picture_path, 'rb'),
                'application/octet-stream'
            )
        }

        # 获取微信返回内容
        response = requests.post(self.WEIXIN_UPLOAD_PICTURE_URL, files=files)
        result = json.loads(response.text)
        # 获取图片的media_id后返回
        return result['media_id']

    def get_media_id(self):
        # ===================================================================================================
        # media_id_cache_path = r'/tmp/media_id_cache'
        # ===================================================================================================
        media_id_cache_path = r'/usr/lib/zabbix/alertscripts/weixin_pic_alarm_cache/media_id_cache'
        timestamp = datetime.strptime(
            self.ZABBIX_ALARM_MESSAGE['alarmtime'], '%Y.%m.%d %H:%M:%S')
        key = self.ZABBIX_ALARM_MESSAGE['eventid'] + \
            timestamp.strftime('%Y%m%d%H%M%S')

        with open(media_id_cache_path, 'r') as file:
            cache = json.loads(file.read())

        media_id = cache.get(str(key))
        if not media_id:
            media_id = self.upload_picture_to_weixin(
                # ===================================================================================================
                # self.get_picture(picture_save_path=r'/tmp/',picture_file_name=(str(key)+'.jpg'))
                # ===================================================================================================
                self.get_picture(picture_save_path=r'/usr/lib/zabbix/alertscripts/weixin_pic_alarm_cache/',
                                 picture_file_name=(str(key) + '.jpg'))
            )

            new_cache = {
                key: media_id
            }

            with open(media_id_cache_path, 'w') as file:
                file.write(json.dumps(new_cache))

        return media_id

    def get_content(self):
        message = ''

        # 定义需要使用的字体颜色格式
        lable_head = '<font color="Chocolate">['
        lable_tail = ']: </font>'
        newline = '<br />'

        # 待推送信息将被定义为以下格式：<font color="Chocolate">[标签头]: </font> 具体告警信息 <br />
        for key, value in self.ZABBIX_ALARM_MESSAGE.items():
            # if key != 'itemid':
            message = message + lable_head + \
                str(key) + lable_tail + str(value) + newline

        # 根据微信接口配置推送内容
        content = {
            "touser": self.WEIXIN_USER_ID,
            "msgtype": "mpnews",
            "agentid": self.WEIXIN_APP_ID,
            "mpnews": {
                "articles": [
                    {
                        "title": self.ZABBIX_ALARM_SUBJECT,
                        # thumb_media_id用于标记需要显示的图片的media_id
                        "thumb_media_id": self.get_media_id(),
                        "author": "Zabbix Server",
                        # "content_source_url": "URL",
                        "content": message,
                        # "digest": "Digest description"
                    }
                ]
            },
            "safe": 0
        }
        return json.dumps(content)

    def push_alarm_to_weixin(self):
        data = (self.get_content()).encode('utf-8')
        push_url = urllib.request.Request(self.WEIXIN_SEND_MESSAGE_URL, data)
        result = urllib.request.urlopen(push_url)
        return result.read()


if __name__ == '__main__':
    user = str(sys.argv[1])     # 接收告警信息的用户名
    subject = str(sys.argv[2])  # 消息标题，这里是zabbix传入的消息标题
    content = str(sys.argv[3])  # 报警信息内容，这里是zabbix传入的告警信息

    # 注意点：
    # 1、content必须的参数有itemid、alarmtime、eventid
    # 2、需要在指定路径下事先设置好media_id_cache文件，内容可以是这样：{"100120181215145949": "3TtUxoOP-IK-rgIXGIXoCoGhLgtICfmYQjtQXGUpFw0Q"}
    # ===================================================================================================
    # user = '12345678'
    # subject = 'test'
    # content = '{"itemid": "23305","alarmtime": "2018.12.15 14:59:49","eventid": "1001","备注": "该告警为测试消息，发自zabbix测试服务器"}'
    # ===================================================================================================
	# {
	# "服务器": "{HOST.NAME}",
	# "主机地址": "{HOST.IP}",
	# "告警时间": "{EVENT.DATE} {EVENT.TIME}",
	# "告警等级": "{TRIGGER.SEVERITY}",
	# "告警信息": "{TRIGGER.NAME}",
	# "告警项目": "{TRIGGER.KEY1}",
	# "问题详情": "{ITEM.NAME}: {ITEM.VALUE}",
	# "当前状态": "{TRIGGER.STATUS}",
	# "事件ID": "{EVENT.ID}",
	# "以下为调试信息":"---分割线---",
	# "itemid": "{ITEM.ID1}",
	# "alarmtime": "{EVENT.DATE} {EVENT.TIME}",
	# "eventid": "{EVENT.ID}"
	# }
	# ===================================================================================================
	# {
	# "服务器": "{HOST.NAME}",
	# "主机地址": "{HOST.IP}",
	# "告警时间": "{EVENT.DATE} {EVENT.TIME}",
	# "恢复时间": "{EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}",
	# "告警等级": "{TRIGGER.SEVERITY}",
	# "恢复信息": "{TRIGGER.NAME} 的问题已恢复",
	# "恢复详情": "{ITEM.NAME}恢复为:{ITEM.VALUE}",
	# "当前状态": "{TRIGGER.STATUS}",
	# "事件ID": "{EVENT.ID}",
	# "以下为调试信息":"---分割线---",
	# "itemid": "{ITEM.ID1}",
	# "alarmtime": "{EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}",
	# "eventid": "{EVENT.ID}"
	# }
	# ===================================================================================================
	
	
    AH = AlarmHandler(
        weixin_user_id=user,
        zabbix_alarm_subject=subject,
        zabbix_alarm_message=content,
        # ===================================================================================================
        zabbix_username='username',
        zabbix_password='password',
        zabbix_login_url=r'http://127.0.0.1/index.php',
        zabbix_get_picture_url=r'http://127.0.0.1/chart.php'
        # ===================================================================================================
    )

    print(AH.push_alarm_to_weixin())

