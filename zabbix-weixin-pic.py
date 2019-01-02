#!/usr/local/bin/python3
# -*- coding:utf-8 -*-

'''
该模块实现zabbix推送微信图文告警的功能

脚本接收3个参数：
    1.接收告警信息的用户名
    2.消息标题，这里是zabbix传入的消息标题
    3.报警信息内容，这里是zabbix传入的告警信息，注意：

        zabbix传入告警消息必须要以json格式传入，且必须包含有
            "itemid"：监控项ID
            "alarmtime"：告警时间
            "eventid"：事件ID
        三个参数，否则脚本无法处理消息
        告警信息参考例子：
            {
                "服务器": "{HOST.NAME}",
                "主机地址": "{HOST.IP}",
                "告警时间": "{EVENT.DATE} {EVENT.TIME}",
                "告警等级": "{TRIGGER.SEVERITY}",
                "告警信息": "{TRIGGER.NAME}",
                "告警项目": "{TRIGGER.KEY1}",
                "当前状态": "{TRIGGER.STATUS}",
                "事件ID": "{EVENT.ID}",
                "itemid": "{ITEM.ID1}",
                "alarmtime": "{EVENT.DATE} {EVENT.TIME}",
                "eventid": "{EVENT.ID}"
            }
        恢复信息参考例子：
            {
                "服务器": "{HOST.NAME}",
                "主机地址": "{HOST.IP}",
                "告警时间": "{EVENT.DATE} {EVENT.TIME}",
                "恢复时间": "{EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}",
                "告警等级": "{TRIGGER.SEVERITY}",
                "恢复信息": "{TRIGGER.NAME} 的问题已恢复",
                "当前状态": "{TRIGGER.STATUS}",
                "事件ID": "{EVENT.ID}",
                "itemid": "{ITEM.ID1}",
                "alarmtime": "{EVENT.RECOVERY.DATE} {EVENT.RECOVERY.TIME}",
                "eventid": "{EVENT.ID}"
            }
        脚本会在处理告警消息的时候将"itemid"，"alarmtime"，"eventid"信息筛选出来后删除，
        其他信息直接推送。

在部署脚本前需要在指定位置创建文件名为alarm_script.cfg和media_id_cache的文件：

    1.media_id_cache：media_id_cache文件路径在alarm_script.cfg中定义，该文件用来缓存已经上传的监控
    图片的mediaid，内容为单行，格式如下：
        {"100120181215145949": "3TtUxoOP-IK-rgIXGIXoCoGhLgtICfmYQjtQXGUpFw0Q"}
    首次部署时可初始化成以上内容，格式需严格按照模板，内容随机即可

    2.alarm_script.cfg为脚本配置文件，定义脚本运行所需的必要配置，使用json格式定义参数，格式如下：
        {
            "weixin_parameter":{
                "corpid":"wx**************8e",
                "secret":"TL*************************************nE",
                "appid":"123",
                "msg_author":"Zabbix Server"
            },

            "zabbix_parameter":{
                "username":"loginusername",
                "password":"loginpassword",
                "login_url":"http://ZabbixServerIP/zabbix/index.php",
                "get_picture_url":"http://ZabbixServerIP/zabbix/chart.php"
            },

            "path_parameter":{
                "picture_save_path":"/usr/lib/zabbix/alertscripts/weixin_pic_alarm_cache/",
                "mediaid_cache_path":"/usr/lib/zabbix/alertscripts/weixin_pic_alarm_cache/media_id_cache"
            }
        }
    参数名必须严格按照配置文件格式书写，配置值按照实际情况配置
'''

import sys
import urllib.request
import urllib.parse
import http.cookiejar
import requests
import json
from datetime import datetime


class AlarmHandler:
'''
告警消息处理类
'''
    def __init__(self,
                 weixin_user_id,
                 zabbix_alarm_subject,
                 zabbix_alarm_message
                 ):
        '''
        构造函数
        weixin_user_id：接收微信告警信息接收用户ID
        zabbix_alarm_subject：告警标题
        zabbix_alarm_message：告警消息内容
        '''

        # 初始化变量
        self.WEIXIN_USER_ID = weixin_user_id

        # 读取配置文件
        with open('/usr/lib/zabbix/alertscripts/alarm_script.cfg', encoding='utf-8') as file:
            config = json.loads(file.read())

        # 从配置文件中获取信息后初始化变量
        self.WEIXIN_CORP_ID = str(config['weixin_parameter']['corpid'])
        self.WEIXIN_SECRET = str(config['weixin_parameter']['secret'])
        self.WEIXIN_APP_ID = str(config['weixin_parameter']['appid'])
        self.WEIXIN_MSG_AUTHOR = str(config['weixin_parameter']['msg_author'])

        self.ZABBIX_USERNAME = str(config['zabbix_parameter']['username'])
        self.ZABBIX_PASSWORD = str(config['zabbix_parameter']['password'])
        self.ZABBIX_LOGIN_URL = str(config['zabbix_parameter']['login_url'])
        self.ZABBIX_GET_PICTURE_URL = str(config['zabbix_parameter']['get_picture_url'])

        self.PICTURE_SAVE_PATH = str(config['path_parameter']['picture_save_path'])
        self.MEDIAID_CACHE_PATH = str(config['path_parameter']['mediaid_cache_path'])

        # 设置获取access_token的URL
        self.GET_WEIXIN_ACCESS_TOKEN_URL = \
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={CORPID}&corpsecret={SECRET}".format(
                CORPID=self.WEIXIN_CORP_ID, SECRET=self.WEIXIN_SECRET)

        # 获取access_token
        response_context = json.loads(urllib.request.urlopen(self.GET_WEIXIN_ACCESS_TOKEN_URL).read().decode('utf-8'))
        self.WEIXIN_ACCESS_TOKEN = response_context['access_token']

        # 设置推送消息的URL
        self.WEIXIN_SEND_MESSAGE_URL = \
            "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={ACCESS_TOKEN}".format(
                ACCESS_TOKEN=self.WEIXIN_ACCESS_TOKEN)

        # 设置上传告警图片的URL
        self.WEIXIN_UPLOAD_PICTURE_URL = \
            "https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={ACCESS_TOKEN}&type=image".format(
                ACCESS_TOKEN=self.WEIXIN_ACCESS_TOKEN)

        # 获取zabbix传输过来的告警
        self.ZABBIX_ALARM_SUBJECT = zabbix_alarm_subject
        self.ZABBIX_ALARM_MESSAGE = json.loads(zabbix_alarm_message)

        # 从告警信息中获取重要参数
        self.ZABBIX_ALARM_ITEMID = self.ZABBIX_ALARM_MESSAGE['itemid']
        self.ZABBIX_ALARM_TIME = self.ZABBIX_ALARM_MESSAGE['alarmtime']
        self.ZABBIX_ALARM_EVENTID = self.ZABBIX_ALARM_MESSAGE['eventid']
        # 获取后删除
        del self.ZABBIX_ALARM_MESSAGE['itemid']
        del self.ZABBIX_ALARM_MESSAGE['alarmtime']
        del self.ZABBIX_ALARM_MESSAGE['eventid']

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

        '''
        获取监控图片函数
        picture_save_path：图片保存路径
        picture_file_name：图片名
        picture_height：图片高度
        picture_width：图片宽度
        picture_period：监控图时长
        函数返回保存图片的绝对路径
        '''

        zabbix_picture_path = picture_save_path + picture_file_name

        values = {
            'itemids[]': self.ZABBIX_ALARM_ITEMID,
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

        '''
        上次监控图片到微信函数
        upload_picture_path：待上传图片的路径
        函数返回微信保存图片的mediaid
        '''

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

        '''
        获取微信mediaid函数
        函数返回微信保存图片的mediaid
        该函数将已经上传的图片的mediaid保存在文件中，以备重复使用
        文件内容以json格式保存，字段名以“zabbix告警的事件ID + 时间戳命名”，精确到秒，如：100120181215145949
        mediaid即是上传图片后微信返回的mediaid
        '''

        # 创建时间戳和字段名
        timestamp = datetime.strptime(self.ZABBIX_ALARM_TIME, '%Y.%m.%d %H:%M:%S')
        key = self.ZABBIX_ALARM_EVENTID + timestamp.strftime('%Y%m%d%H%M%S')

        # 读取缓存文件
        with open(self.MEDIAID_CACHE_PATH, 'r') as file:
            cache = json.loads(file.read())

        # 直接查找其中有没有保存着对应的mediaid，如果没有，则调用上传图片函数，并将相应的mediaid写入文件
        media_id = cache.get(str(key))
        if not media_id:
            media_id = self.upload_picture_to_weixin(
                self.get_picture(picture_save_path=self.PICTURE_SAVE_PATH, picture_file_name=(str(key) + '.jpg'))
            )

            new_cache = {
                key: media_id
            }

            with open(self.MEDIAID_CACHE_PATH, 'w') as file:
                file.write(json.dumps(new_cache))

        return media_id

    def get_content(self):

        '''
        获取推送微信消息的函数
        函数返回待推送微信的消息内容
        '''

        message = ''

        # 定义需要使用的字体颜色格式
        lable_head = '<font color="Chocolate">['
        lable_tail = ']: </font>'
        newline = '<br />'

        # 待推送信息将被定义为以下格式：<font color="Chocolate">[标签头]: </font> 具体告警信息 <br />
        for key, value in self.ZABBIX_ALARM_MESSAGE.items():
            message = message + lable_head + str(key) + lable_tail + str(value) + newline

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
                        "author": self.WEIXIN_MSG_AUTHOR,
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

        '''
        向微信推送消息函数
        返回推送结果
        '''

        data = (self.get_content()).encode('utf-8')
        push_url = urllib.request.Request(self.WEIXIN_SEND_MESSAGE_URL, data)
        result = urllib.request.urlopen(push_url)
        return result.read()


if __name__ == '__main__':
    user = str(sys.argv[1])     # 接收告警信息的用户名
    subject = str(sys.argv[2])  # 消息标题，这里是zabbix传入的消息标题
    content = str(sys.argv[3])  # 报警信息内容，这里是zabbix传入的告警信息

    AH = AlarmHandler(
        weixin_user_id=user,
        zabbix_alarm_subject=subject,
        zabbix_alarm_message=content
    )

    print(AH.push_alarm_to_weixin())
