import asyncio
import re
import json
import os
import time
import aiohttp
import logging
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, ChatInviteAlready, ChatInvite, MessageEntityTextUrl
from telethon.errors import SessionPasswordNeededError, FloodWaitError, RPCError, ChannelPrivateError
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from urllib.parse import urlparse, parse_qs

# ====== 用户配置区域 ======
API_ID = 27335138
API_HASH = '2459555ba95421148c682e2dc3031bb6'
STRING_SESSION = '1BVtsOJYBuxvWKzU2s5RM2JAvD1OUh0Ks20deYaWNpehYUVvPjAC-As-8DM9yt5_DdsTMOcZ5R-4CL-T6foBVPwJ3pmWlaqW_iBkfChzidstU2OVChHWwvhMEURKBACRJDZT2U6Jr7f-DtbjqQnEK63_OUFAQHpSjNkCVdkLeq9WNCJtLr9zyC660qk5xzPWcjMMREihQGkV6irPtiyX6xgeIjBDqToq4qUcGCir_m4NcZ0cbfHnoeDcYNz9FJGlHaXvBRamE75sQ2PCdGCuUE0-JuW5m6VMMzXZHuUs_R4vPYhUm61P_IsJg4yCljK1txz_rl6TsYqkcofPvhPNv1zm895UUloI='   # 从https://tgs.252035.xyz/获取，把V1填入 ,必填项！！！！！！！！！！！！

# 自定义monitor_state和sent_links的保存路径（如果为空则保存在脚本所在目录）
SAVE_PATH = ""  # 示例: "/path/to/save/directory"

# 频道配置（逗号隔开）
CHANNEL_URLS = [
    'https://t.me/tianyifc','https://t.me/yp123pan','https://t.me/lubaoty','https://t.me/bh9_527'
]

MONITOR_INTERVAL = 1200  # 循环周期3600秒
DEBUG = False  # 调试模式开关

# API2开关 - True为启用，False为禁用
ENABLE_API2 = True

# 全局排除关键词
EXCLUDE_KEYWORDS = ['小程序', '预告', '预感', '盈利', '即可观看', '书籍', '电子书', '图书', '丛书', '期刊','app','软件', '破解版','解锁','专业版','高级版','最新版','食谱',
              '免安装', '免广告','安卓', 'Android', '课程', '作品', '教程', '教学', '全书', '名著', 'mobi', 'MOBI', 'epub','任天堂','PC','单机游戏',
              'pdf', 'PDF', 'PPT', '抽奖', '完整版', '有声书','读者','文学', '写作', '节课', '套装', '话术', '纯净版', '日历''txt', 'MP3','网赚',
              'mp3', 'WAV', 'CD', '音乐', '专辑', '模板', '书中', '读物', '入门', '零基础', '常识', '电商', '小红书','JPG','短视频','工作总结',
              '写真','抖音', '资料', '华为', '短剧', '纪录片', '记录片', '纪录', '纪实', '学习', '付费', '小学', '初中','数学', '语文', '唐诗','魔法坏女巫','车载','DJ','合并']  # 可根据需要添加更多黑名单关键词

# API配置列表
API_CONFIGS = [
    # API1配置（提取剧集）
    {
        'url': "http://192.168.2.17:4567/#/shares/",  #仅作示例，AT宿主机IP:外部端口/api/shares，必填项！！！！！！！！！！！！
        'key': "2879bf4d900f45e5bed3d4167668e4d1",                 #AT高级设置中获取，必填项！！！！！！！！！！！！
        'required_keywords': [],  # API1必须关键词
        'optional_keywords': ["季", "集", "EP","S0","动漫"],   # API1可选关键词
        'monitor_days': 120,
        'try_join': True,
        'monitor_limit': 2000
    },
    # API2配置（提取电影）
    {
        'url': "http://192.168.2.17:4567/#/shares/",  # 同API1，必填项！！！！！！！！！！！！
        'key': "2879bf4d900f45e5bed3d4167668e4d1",                                     # 同API1，必填项！！！！！！！！！！！！
        'required_keywords': [],                       # API2必须关键词（空）
        'optional_keywords': ["原盘", "简繁", "简英","简中","双语","REMUX","电影"],                       # API2可选关键词
        'monitor_days': 300,
        'try_join': True,
        'monitor_limit': 5000
    }
]

# ====== 用户配置区域结束 ======

# 为每个频道创建独立标识符
def get_channel_identifier(channel_url):
    """生成频道URL的唯一标识符"""
    # 移除协议和特殊字符
    identifier = re.sub(r'https?://', '', channel_url)
    identifier = re.sub(r'[^\w\-]', '_', identifier)
    return identifier[:50]  # 限制长度

# 根据频道标识符生成状态文件前缀
def get_state_file(channel_id, api_index, cloud_type):
    """获取指定频道、API和云盘类型的状态文件名"""
    prefix = f"{channel_id}_monitor_state_api"
    if cloud_type == 'tianyi':
        return get_full_path(f"{prefix}{api_index+1}_tianyi.json")
    elif cloud_type == 'uc':
        return get_full_path(f"{prefix}{api_index+1}_uc.json")
    elif cloud_type == '123':  
        return get_full_path(f"{prefix}{api_index+1}_123.json")
    else:
        return None

def get_sent_links_file(channel_id, api_index, cloud_type):
    """获取指定频道、API和云盘类型的已发送链接文件名"""
    prefix = f"{channel_id}_sent_links_api"
    if cloud_type == 'tianyi':
        return get_full_path(f"{prefix}{api_index+1}_tianyi.json")
    elif cloud_type == 'uc':
        return get_full_path(f"{prefix}{api_index+1}_uc.json")
    elif cloud_type == '123': 
        return get_full_path(f"{prefix}{api_index+1}_123.json")
    else:
        return None

def get_full_path(filename):
    """获取完整的文件路径（考虑自定义保存路径）"""
    if SAVE_PATH and os.path.isdir(SAVE_PATH):
        return os.path.join(SAVE_PATH, filename)
    return filename

# 优化提取码正则表达式（精确匹配4-6位字符）
access_pattern = r'(?:密码|提取码|验证码|访问码|分享密码|密钥|pwd|password|share_pwd|pass_code|#)[=:：\s]*([a-zA-Z0-9]{4,6})(?![a-zA-Z0-9])'

AD_PATTERNS = [
    r'天翼云盘.*资源分享',
    r'via\s*🤖編號\s*9527',
    r'🏷?\s*标签\s*：.*',
    r'[🏷#]\s*\w+'
]

UC_AD_PATTERNS = [
    r'UC网盘.*分享',
    r'资源编号：\d+',
    r'🏷️?\s*标签\s*：.*',
    r'[🏷#]\s*\w+'
]

PAN123_AD_PATTERNS = [  
    r'123网盘.*分享',
    r'资源编号：\d+',
    r'🏷️?\s*标签\s*：.*',
    r'[🏷#]\s*\w+'
]

# 修正：123网盘链接正则表达式（支持更多格式）
PAN123_LINK_PATTERN = r'(?:https?://)?(?:www\.)?(?:123[\d]*|pan\.123)\.com/s/([a-zA-Z0-9\-_]+)'

def clean_task_name(text, cloud_type):
    """深度清理任务名称，移除特殊字符和广告文案（保留空格）"""
    # 根据不同云盘类型使用不同的广告模式
    if cloud_type == 'tianyi':
        patterns = AD_PATTERNS
    elif cloud_type == 'uc':
        patterns = UC_AD_PATTERNS
    elif cloud_type == '123':  
        patterns = PAN123_AD_PATTERNS
    else:
        patterns = []
    
    # 移除广告文案
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # 根据不同云盘类型移除分享链接
    if cloud_type == 'tianyi':
        text = re.sub(r'https?://cloud\.189\.cn/t/[a-zA-Z0-9]{12}', '', text)
        text = re.sub(r'cloud\.189\.cn/t/[a-zA-Z0-9]{12}', '', text)
    elif cloud_type == 'uc':
        text = re.sub(r'https?://drive\.uc\.cn/s/[a-zA-Z0-9\-_]+', '', text)
        text = re.sub(r'drive\.uc\.cn/s/[a-zA-Z0-9\-_]+', '', text)
    elif cloud_type == '123':  
        # 使用修正后的正则表达式
        text = re.sub(PAN123_LINK_PATTERN, '', text, flags=re.IGNORECASE)
    
    # 移除特殊字符（保留中文、字母、数字、空格和常用标点）
    # 修改：保留空格和中文空格（\u3000）
    text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9,，.。!！?？:：《》()（）【】\s\u3000]', '', text)
    
    # 移除开头和结尾的特殊空格（保留中间空格）
    # 修改：不再移除所有空格，只移除开头结尾的特殊空格
    text = re.sub(r'^[\s\u3000]+|[\s\u3000]+$', '', text)
    
    # 截断长度调整为195（为后缀预留空间）
    return text.strip()[:195]

def extract_cloud_info(message):
    """从Telegram消息中提取云盘分享信息，支持多链接独立描述和超链接参数提取码"""
    text = message.message
    if not text:
        return []
        
    results = []
    
    # 解码URL编码的特殊字符
    decoded_text = text.replace('%EF%BC%88', '(').replace('%EF%BC%89', ')')
    
    # 尝试提取公共标题（第一行文本）
    lines = decoded_text.split('\n')
    common_title = clean_task_name(lines[0], 'tianyi') if lines else ''  # 初始使用天翼清理逻辑
    
    # 使用优化后的正则表达式提取提取码
    access_match = re.search(access_pattern, decoded_text, re.IGNORECASE)
    common_access_code = access_match.group(1) if access_match else None
    
    # 1. 提取天翼云链接
    tianyi_results = extract_cloud_links(
        decoded_text, 
        common_title,
        common_access_code,
        r'(?:https?://)?cloud\.189\.cn/t/([a-zA-Z0-9]{12})\b',
        'tianyi'
    )
    
    # 2. 提取UC链接
    uc_results = extract_cloud_links(
        decoded_text,
        common_title,
        common_access_code,
        r'drive\.uc\.cn/s/([a-zA-Z0-9\-_]+)([^#]*)?(#*/list/share/([^\?\-]+))?',
        'uc'
    )
    
    # 3. 提取123网盘链接（新增123网盘支持）
    # 使用修正后的正则表达式
    pan123_results = extract_cloud_links(
        decoded_text,
        common_title,
        common_access_code,
        PAN123_LINK_PATTERN,  
        '123'
    )
    
    results.extend(tianyi_results)
    results.extend(uc_results)
    results.extend(pan123_results)  
    
    # 4. 处理所有类型的超链接（增强提取码提取功能）
    if message.entities:
        for entity in message.entities:
            if isinstance(entity, MessageEntityTextUrl):
                url = entity.url
                # 提取实体对应的文本
                entity_text = text[entity.offset:entity.offset+entity.length]
                
                # 从URL参数中提取提取码（新增功能）
                url_access_code = extract_access_code_from_url(url)
                
                # 天翼云链接
                tianyi_match = re.search(r'cloud\.189\.cn/t/([a-zA-Z0-9]{12})', url, re.IGNORECASE)
                if tianyi_match:
                    share_code = tianyi_match.group(1)
                    # 添加到结果（如果未包含）
                    if not any(info['share_code'] == share_code and info['cloud_type'] == 'tianyi' for info in results):
                        results.append({
                            'share_code': share_code,
                            'description': entity_text,
                            'access_code': url_access_code or common_access_code,
                            'common_title': common_title,
                            'cloud_type': 'tianyi'
                        })
                
                # UC链接
                uc_match = re.search(r'drive\.uc\.cn/s/([a-zA-Z0-9\-_]+)', url, re.IGNORECASE)
                if uc_match:
                    share_code = uc_match.group(1)
                    # 添加到结果（如果未包含）
                    if not any(info['share_code'] == share_code and info['cloud_type'] == 'uc' for info in results):
                        results.append({
                            'share_code': share_code,
                            'description': entity_text,
                            'access_code': url_access_code or common_access_code,
                            'common_title': common_title,
                            'cloud_type': 'uc'
                        })
                
                # 修正：123网盘链接提取（使用更全面的正则）
                pan123_match = re.search(PAN123_LINK_PATTERN, url, re.IGNORECASE)
                if pan123_match:
                    share_code = pan123_match.group(1)
                    # 添加到结果（如果未包含）
                    if not any(info['share_code'] == share_code and info['cloud_type'] == '123' for info in results):
                        results.append({
                            'share_code': share_code,
                            'description': entity_text,
                            'access_code': url_access_code or common_access_code,
                            'common_title': common_title,
                            'cloud_type': '123'
                        })
    
    return results

def extract_access_code_from_url(url):
    """从URL参数中提取访问码（增强功能）"""
    # 解析URL参数
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # 检查可能的提取码参数名
        for param in ['pwd', 'password', 'access_code', 'code', 'sharepwd']:
            if param in query_params and query_params[param]:
                code = query_params[param][0]
                # 验证提取码格式（4-6位字母数字）
                if re.match(r'^[a-zA-Z0-9]{4,6}$', code):
                    return code
    except Exception:
        pass
    
    # 使用正则作为备选方案
    pattern = r'[?&](?:pwd|password|access_code|code|sharepwd)=([a-zA-Z0-9]{4,6})'
    match = re.search(pattern, url, re.IGNORECASE)
    return match.group(1) if match else None

def extract_cloud_links(decoded_text, common_title, common_access_code, pattern, cloud_type):
    """提取特定云盘的链接（增强访问码提取功能）"""
    results = []
    # 添加忽略大小写标志，确保匹配Markdown超链接
    share_matches = re.finditer(pattern, decoded_text, re.IGNORECASE)
    
    for match in share_matches:
        full_url = match.group(0)  # 获取完整URL
        share_code = match.group(1)
        
        # 从URL中提取访问码
        url_access_code = extract_access_code_from_url(full_url)
        
        # 查找分享码前面的描述文本
        start_index = match.start()
        context_start = max(0, start_index - 100)
        context_text = decoded_text[context_start:start_index]
        
        # 关键修改：优先检查上一行文本
        prev_line = ""
        if '\n' in context_text:
            lines = context_text.split('\n')
            if len(lines) > 1:
                prev_line = lines[-2].strip()  # 获取上一行文本

        # 判断逻辑：
        # 1. 如果有上一行文本且长度>=30，视为分享链接的标题
        # 2. 否则视为描述，存在公共标题
        if prev_line and len(prev_line) >= 30:
            description = prev_line
            # 当被视为标题时，清除公共标题
            current_common_title = ''
        else:
            # 提取链接前的文本（最多50字符）
            prefix_match = re.search(r'([^\n]{0,50})$', context_text)
            description = prefix_match.group(1).strip() if prefix_match else ""
            # 保留公共标题
            current_common_title = common_title         
        
        # 清理描述文本（保留空格）
        # 修改：不再移除空格
        clean_desc = clean_task_name(description, cloud_type)
        
        # 从上下文中提取访问码（优先级高于全局访问码）
        context_access_match = re.search(access_pattern, context_text, re.IGNORECASE)
        context_access_code = context_access_match.group(1) if context_access_match else None
        
        # 确定最终的访问码（优先级：URL参数 > 上下文 > 全局）
        final_access_code = url_access_code or context_access_code or common_access_code
        
        results.append({
            'share_code': share_code,
            'description': clean_desc,
            'access_code': final_access_code,
            'common_title': current_common_title,
            'cloud_type': cloud_type
        })
    
    return results

def filter_message(text, api_cfg, api_index):
    """根据API配置筛选消息（优化API2逻辑）并返回过滤结果和原因"""
    required_keywords = api_cfg['required_keywords']
    optional_keywords = api_cfg['optional_keywords']
    reason = ""
    
    # API1: 标准过滤逻辑
    if api_index == 0:
        # 检查必须包含的关键词
        for keyword in required_keywords:
            if keyword and keyword not in text:
                reason = f"缺少必须关键词 '{keyword}'"
                return False, reason
        
        # 检查可选关键词（至少包含一个）
        if optional_keywords:
            found_optional = False
            for keyword in optional_keywords:
                if keyword and keyword in text:
                    found_optional = True
                    break
            if not found_optional:
                optional_str = ", ".join([kw for kw in optional_keywords if kw])
                reason = f"未找到任何可选关键词: [{optional_str}]"
                return False, reason
        
        return True, "满足所有过滤条件"
    
    # API2过滤逻辑
    elif api_index == 1:
        # 1. 动态排除API1的可选关键词
        api1_optional = API_CONFIGS[0]['optional_keywords']
        
        for keyword in api1_optional:
            if keyword and keyword in text:
                reason = f"包含API1排除关键词 '{keyword}'"
                return False, reason
        
        # 2. 检查API2的必须关键词（如果有）
        for keyword in required_keywords:
            if keyword and keyword not in text:
                reason = f"缺少必须关键词 '{keyword}'"
                return False, reason
        
        # 3. 检查API2的可选关键词（如果有）
        if optional_keywords:
            found_optional = False
            for keyword in optional_keywords:
                if keyword and keyword in text:
                    found_optional = True
                    break
            if not found_optional:
                optional_str = ", ".join([kw for kw in optional_keywords if kw])
                reason = f"未找到任何可选关键词: [{optional_str}]"
                return False, reason
        
        return True, "满足所有过滤条件"  # 通过所有检查
    
    return False, "未识别的API索引"

async def connect_telegram_with_retry():
    """带重试机制的Telegram连接"""
    max_retries = 5
    retry_delay = 10
    
    for attempt in range(max_retries):
        try:
            client = TelegramClient(
                StringSession(STRING_SESSION), 
                API_ID, 
                API_HASH
            )
            await client.start()
            print("成功连接到Telegram")
            return client
        except SessionPasswordNeededError:
            print("需要两步验证，请在Telegram应用中确认登录")
            await client.start(password=lambda: input('请输入两步验证密码: '))
            return client
        except FloodWaitError as e:
            wait_time = e.seconds + 10
            print(f"遇到限流，等待 {wait_time} 秒后重试...")
            await asyncio.sleep(wait_time)
        except RPCError as e:
            print(f"连接失败 ({e}), 尝试 {attempt+1}/{max_retries}")
            await asyncio.sleep(retry_delay)
        except Exception as e:
            print(f"未知错误: {e}, 尝试 {attempt+1}/{max_retries}")
            await asyncio.sleep(retry_delay)
    
    print("连接失败，达到最大重试次数")
    return None

def load_processed_messages(channel_id, api_index, cloud_type):
    """加载指定频道、API和云盘类型的已处理消息ID"""
    state_file = get_state_file(channel_id, api_index, cloud_type)
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                return set(json.load(f))
        except Exception as e:
            print(f"加载状态文件{state_file}失败: {e}")
    return set()

def save_processed_messages(processed_ids, channel_id, api_index, cloud_type):
    """保存指定频道、API和云盘类型的已处理消息ID"""
    state_file = get_state_file(channel_id, api_index, cloud_type)
    try:
        with open(state_file, 'w') as f:
            json.dump(list(processed_ids), f)
    except Exception as e:
        print(f"保存状态文件{state_file}失败: {e}")

def load_sent_links(channel_id, api_index, cloud_type):
    """加载指定频道、API和云盘类型的已发送分享链接记录"""
    sent_links_file = get_sent_links_file(channel_id, api_index, cloud_type)
    if os.path.exists(sent_links_file):
        try:
            with open(sent_links_file, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_sent_links(sent_links, channel_id, api_index, cloud_type):
    """保存指定频道、API和云盘类型的已发送分享链接记录"""
    sent_links_file = get_sent_links_file(channel_id, api_index, cloud_type)
    try:
        with open(sent_links_file, 'w') as f:
            json.dump(list(sent_links), f)
    except Exception as e:
        print(f"保存已发送链接记录到{sent_links_file}失败: {e}")

async def get_channel_entity(client, channel_url, api_cfg):
    """根据频道URL获取频道实体"""
    try:
        # 尝试直接使用完整URL获取实体
        try:
            entity = await client.get_entity(channel_url)
            print(f"成功获取频道实体: {entity.title}")
            return entity
        except ValueError:
            pass
        
        # 处理邀请链接格式
        if '+' in channel_url:
            invite_hash = channel_url.split('+')[-1]
            try:
                invite = await client(CheckChatInviteRequest(invite_hash))
                if isinstance(invite, ChatInviteAlready):
                    print(f"已加入频道: {invite.chat.title}")
                    return invite.chat
                elif isinstance(invite, ChatInvite) and api_cfg['try_join']:
                    print(f"尝试加入私有频道: {channel_url}")
                    result = await client(ImportChatInviteRequest(invite_hash))
                    if result and hasattr(result, 'chats') and result.chats:
                        print(f"成功加入频道: {result.chats[0].title}")
                        return result.chats[0]
            except Exception as e:
                print(f"处理邀请链接失败: {e}")
        else:
            username = channel_url.split('/')[-1]
            try:
                entity = await client.get_entity(f"@{username}")
                print(f"成功获取频道实体: {entity.title}")
                return entity
            except ValueError:
                entity = await client.get_entity(username)
                print(f"成功获取频道实体: {entity.title}")
                return entity
    except ValueError as ve:
        print(f"获取频道实体失败(ValueError): {ve}")
    except Exception as e:
        print(f"获取频道实体失败: {e}")
    return None

async def send_to_api(api_cfg, share_code, task_name, api_index, cloud_type, access_code=None):
    """发送分享链接到API接口（增强错误处理）"""
    # 根据API索引添加目录前缀
    if api_index == 0:
        path_prefix = "追剧/"
    elif api_index == 1:
        path_prefix = "电影/"
    else:
        path_prefix = ""
    
    # 组合完整路径（确保不超过200字符）
    full_path = path_prefix + task_name
    if len(full_path) > 200:
        full_path = full_path[:200]
    
    if cloud_type == 'tianyi':
        share_link = f"https://cloud.189.cn/t/{share_code}"
        cloud_type_id = 9
    elif cloud_type == 'uc':
        share_link = f"https://drive.uc.cn/s/{share_code}"
        cloud_type_id = 7  
    elif cloud_type == '123':  
        # 使用固定域名格式，实际API会正确处理所有123xxx.com域名
        share_link = f"https://www.123865.com/s/{share_code}"
        cloud_type_id = 3  
    
    payload = {
        "path": full_path,  # 使用带前缀的完整路径
        "shareId": share_code,
        "folderId": "",
        "password": access_code if access_code else "",
        "type": cloud_type_id
    }
    
    headers = {
        "x-api-key": api_cfg['key'],
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(api_cfg['url'], json=payload, headers=headers) as response:
                # 获取HTTP状态码
                status = response.status
                raw_response = await response.text()
                
                try:
                    json_response = json.loads(raw_response)
                except json.JSONDecodeError:
                    json_response = {"raw_response": raw_response}
                
                # 仅检查HTTP状态码是否为200
                if status == 200:
                    print(f"✅ 成功发送{cloud_type.upper()}链接到API{api_index+1}: {share_link}")
                    print(f"任务名称: {full_path}")  # 显示带前缀的完整路径
                    print(f"访问码: {access_code or '无'}")
                    print(f"HTTP状态码: {status}")
                    if DEBUG:  # 使用全局调试模式
                        print("API返回值:")
                        print(json.dumps(json_response, indent=2, ensure_ascii=False))
                    return True, json_response
                else:
                    # 增强错误信息输出
                    error_msg = json_response.get("error", "未知错误") if isinstance(json_response, dict) else "非JSON响应"
                    print(f"❌ API{api_index+1}返回失败({cloud_type.upper()}): {share_link}")
                    print(f"HTTP状态码: {status}")
                    print(f"错误类型: {error_msg}")
                    print(f"任务名称: {full_path}")  # 显示带前缀的完整路径
                    print(f"访问码: {access_code or '无'}")
                    
                    # 打印完整的服务器响应
                    print(f"完整响应内容:")
                    print(raw_response)
                    
                    # 调试模式下打印JSON格式的响应
                    if DEBUG:
                        print("JSON格式的响应:")
                        print(json.dumps(json_response, indent=2, ensure_ascii=False))
                    
                    return False, json_response
    except aiohttp.ClientError as e:
        print(f"⚠️ 请求失败({cloud_type.upper()}): {e}, 链接: {share_link}")
        print(f"任务名称: {full_path}")  # 显示带前缀的完整路径
        print(f"访问码: {access_code or '无'}")
        return False, {"error": str(e)}
    except Exception as e:
        print(f"⚠️ 处理请求时出错({cloud_type.upper()}): {e}, 链接: {share_link}")
        print(f"任务名称: {full_path}")  # 显示带前缀的完整路径
        print(f"访问码: {access_code or '无'}")
        return False, {"error": str(e)}

async def process_channel_for_api(client, channel_url, api_cfg, api_index):
    """为特定API处理频道消息（支持多链接独立命名和多频道独立状态）"""
    # 获取频道标识符
    channel_id = get_channel_identifier(channel_url)
    
    print(f"\n处理频道: {channel_url} (API{api_index+1})")
    print(f"频道ID: {channel_id}")
    print(f"时间范围: {api_cfg['monitor_days']}天 | 消息限制: {api_cfg['monitor_limit']}条")
    
    # 加载状态（使用频道特定文件）
    processed_ids_tianyi = load_processed_messages(channel_id, api_index, 'tianyi')
    processed_ids_uc = load_processed_messages(channel_id, api_index, 'uc')
    processed_ids_123 = load_processed_messages(channel_id, api_index, '123')  
    
    # 加载已发送链接（使用频道特定文件）
    sent_links_tianyi = load_sent_links(channel_id, api_index, 'tianyi')
    sent_links_uc = load_sent_links(channel_id, api_index, 'uc')
    sent_links_123 = load_sent_links(channel_id, api_index, '123')  
    
    # 计数器
    processed_count = 0
    sent_count = 0
    skip_count = 0
    
    # 新增：详细原因统计
    skip_reasons = {
        "global_exclude": {},
        "api_filter": {},
        "no_valid_links": 0,
        "already_sent": 0
    }
    
    try:
        # 获取频道实体
        entity = await get_channel_entity(client, channel_url, api_cfg)
        if not entity:
            print(f"无法获取频道实体: {channel_url}")
            return 0, 0
        
        # 计算时间范围
        now = datetime.now(timezone.utc)
        min_date = now - timedelta(days=api_cfg['monitor_days'])
        print(f"监控时间范围: {min_date.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}")
        
        # 收集消息（按照当前API的限制） 
        new_messages = []
        try:
            # 使用iter_messages获取消息（使用当前API的限制）
            async for message in client.iter_messages(entity, limit=api_cfg['monitor_limit']):
                # 跳过已处理或过期的消息
                if ((message.id in processed_ids_tianyi and message.id in processed_ids_uc and message.id in processed_ids_123) or 
                    message.date < min_date.replace(tzinfo=timezone.utc)):
                    continue
                
                new_messages.append(message)
                
            print(f"找到 {len(new_messages)} 条满足当前API限制的新消息")
            
        except ChannelPrivateError:
            # 特殊处理私有频道
            print(f"检测到私有频道，尝试获取最新消息...")
            try:
                async for message in client.iter_messages(entity, limit=100):
                    if ((message.id in processed_ids_tianyi and message.id in processed_ids_uc and message.id in processed_ids_123) or 
                        message.date < min_date.replace(tzinfo=timezone.utc)):
                        continue
                    new_messages.append(message)
                    
                print(f"找到 {len(new_messages)} 条满足当前API限制的新消息")
                
            except Exception as e:
                print(f"获取私有频道消息失败: {e}")
                return 0, 0
                
        except Exception as e:
            print(f"获取消息时出错: {e}")
            return 0, 0
        
        # 处理新消息
        for msg in new_messages:
            if not msg.text:
                continue
            
            # 新增：检查排除关键词（全局过滤）并记录具体关键词
            excluded_keyword = None
            for exclude_kw in EXCLUDE_KEYWORDS:
                if exclude_kw in msg.text:
                    excluded_keyword = exclude_kw
                    skip_reasons["global_exclude"][excluded_keyword] = skip_reasons["global_exclude"].get(excluded_keyword, 0) + 1
                    print(f"⚠️ 消息ID={msg.id} 包含排除关键词 '{excluded_keyword}'，跳过处理")
                    processed_ids_tianyi.add(msg.id)
                    processed_ids_uc.add(msg.id)
                    processed_ids_123.add(msg.id)
                    skip_count += 1
                    break
            
            if excluded_keyword:
                continue
            
            # 打印消息内容
            msg_text = msg.text[:100] + '...' if len(msg.text) > 100 else msg.text
            print(f"消息ID={msg.id}, 时间={msg.date.astimezone().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 应用当前API的过滤规则并获取原因
            filter_result, filter_reason = filter_message(msg.text, api_cfg, api_index)
            if not filter_result:
                # 记录过滤原因
                skip_reasons["api_filter"][filter_reason] = skip_reasons["api_filter"].get(filter_reason, 0) + 1
                print(f"消息ID={msg.id} 未通过API{api_index+1}过滤: {filter_reason}，标记为已处理")
                processed_ids_tianyi.add(msg.id)
                processed_ids_uc.add(msg.id)
                processed_ids_123.add(msg.id)
                skip_count += 1
                continue
            
            # 提取云盘信息
            cloud_infos = extract_cloud_info(msg)
            if not cloud_infos:
                skip_reasons["no_valid_links"] += 1
                print(f"消息ID={msg.id} 未发现有效云盘链接，标记为已处理")
                processed_ids_tianyi.add(msg.id)
                processed_ids_uc.add(msg.id)
                processed_ids_123.add(msg.id)
                skip_count += 1
                continue
            
            processed_count += 1
            print(f"发现有效消息: ID={msg.id} (满足API{api_index+1}过滤条件)")
            print(f"包含 {len(cloud_infos)} 个分享链接")
            
            # 初始化成功标志
            has_success = False
            all_links_skipped = True  # 新增：跟踪所有链接是否都是跳过状态
            
            # 处理每个云盘链接
            for cloud_info in cloud_infos:
                cloud_type = cloud_info['cloud_type']
                share_code = cloud_info['share_code']
                description = cloud_info['description']
                access_code = cloud_info.get('access_code')
                common_title = cloud_info.get('common_title', '')
                
                # 获取当前云盘类型的已处理ID和已发送链接
                if cloud_type == 'tianyi':
                    processed_ids = processed_ids_tianyi
                    sent_links = sent_links_tianyi
                elif cloud_type == 'uc':
                    processed_ids = processed_ids_uc
                    sent_links = sent_links_uc
                elif cloud_type == '123': 
                    processed_ids = processed_ids_123
                    sent_links = sent_links_123
                
                # 清理描述文本（保留空格）
                # 修改：调用clean_task_name函数（已修改为保留空格）
                clean_desc = clean_task_name(description, cloud_type) if description else ""
                
                # 构建任务名称
                if common_title and clean_desc:
                    # 当清理后的描述与公共标题不同时合并
                    if clean_desc != common_title:
                        task_name = f"{common_title}+{clean_desc}"
                    else:
                        task_name = common_title
                elif common_title:
                    task_name = common_title
                elif clean_desc:
                    task_name = clean_desc
                else:
                    task_name = f"{cloud_type.upper()}云资源分享"
                
                # 追加分享码后缀确保唯一性
                task_name = f"{task_name}_{share_code[-4:]}"  
                task_name = task_name[:200]  # 最终长度控制
                
                # 生成分享链接
                if cloud_type == 'tianyi':
                    share_link = f"https://cloud.189.cn/t/{share_code}"
                elif cloud_type == 'uc':
                    share_link = f"https://drive.uc.cn/s/{share_code}"
                elif cloud_type == '123':  
                    share_link = f"https://www.123865.com/s/{share_code}"
                
                # 检查是否已发送过（当前API）
                if share_link in sent_links:
                    skip_reasons["already_sent"] += 1
                    print(f"⏭️ 跳过API{api_index+1}已发送的{cloud_type.upper()}链接: {task_name} - {share_link}")
                    has_success = True  # 已发送过的链接视为成功
                    continue
                
                all_links_skipped = False  # 至少有一个链接需要处理
                
                # 发送到当前API
                api_success, _ = await send_to_api(
                    api_cfg, share_code, task_name, api_index, 
                    cloud_type, access_code
                )
                
                if api_success:
                    sent_links.add(share_link)
                    sent_count += 1
                    has_success = True  # 标记至少有一个成功
                    print(f"✅ 已记录{cloud_type.upper()}链接到API{api_index+1}: {share_link}")
                    print(f"任务名称: {task_name}")  # 注意：这里显示原始任务名，但发送的实际路径带前缀
                else:
                    print(f"⚠️ 发送{cloud_type.upper()}链接失败: {share_link}")
            
            # 处理成功状态
            if has_success:
                processed_ids_tianyi.add(msg.id)
                processed_ids_uc.add(msg.id)
                processed_ids_123.add(msg.id)
                if all_links_skipped:
                    print(f"消息ID={msg.id} 所有链接都已发送过，标记为已处理")
                else:
                    print(f"消息ID={msg.id} 至少有一个链接发送成功，标记为已处理")
            else:
                print(f"消息ID={msg.id} 所有链接发送失败，将保留以便下次尝试")
        
        # 保存状态（使用频道特定文件）
        save_processed_messages(processed_ids_tianyi, channel_id, api_index, 'tianyi')
        save_processed_messages(processed_ids_uc, channel_id, api_index, 'uc')
        save_processed_messages(processed_ids_123, channel_id, api_index, '123')  
        save_sent_links(sent_links_tianyi, channel_id, api_index, 'tianyi')
        save_sent_links(sent_links_uc, channel_id, api_index, 'uc')
        save_sent_links(sent_links_123, channel_id, api_index, '123')  
        
        # 新增：API处理后的详细统计（增加东八区时间戳）[[38][37]]
        # 获取东八区当前时间
        tz_east8 = timezone(timedelta(hours=8))
        current_time = datetime.now(tz_east8).strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"\n📅 处理完成时间（东八区）: {current_time}")
        print(f"📊 API{api_index+1} 处理汇总统计:")
        print(f"✓ 处理消息总数: {len(new_messages)}")
        print(f"✓ 跳过消息数: {skip_count}")
        print(f"✓ 成功处理消息数: {processed_count}")
        print(f"✓ 发送链接数: {sent_count}")
        
        if skip_reasons["global_exclude"]:
            print("\n⛔ 排除关键词统计:")
            for keyword, count in skip_reasons["global_exclude"].items():
                print(f"  - 包含 '{keyword}': {count} 条")
        
        if skip_reasons["api_filter"]:
            print("\n⚠️ API过滤原因统计:")
            for reason, count in skip_reasons["api_filter"].items():
                print(f"  - {reason}: {count} 条")
        
        if skip_reasons["no_valid_links"] > 0:
            print(f"\n🔍 未发现有效云盘链接: {skip_reasons['no_valid_links']} 条")
        
        if skip_reasons["already_sent"] > 0:
            print(f"\n⏭️ 已发送链接跳过: {skip_reasons['already_sent']} 个")
        
        return processed_count, sent_count
    
    except Exception as e:
        print(f"处理频道 {channel_url} 时出错: {e}")
        return processed_count, sent_count

async def continuous_monitoring():
    """持续监控频道的新消息（支持多API处理）"""
    # 每个API使用独立的状态
    while True:
        # 获取东八区当前时间
        tz_east8 = timezone(timedelta(hours=8))
        current_time = datetime.now(tz_east8).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n⏰ {current_time} - 开始监控周期")
        
        client = await connect_telegram_with_retry()
        if not client:
            print("无法连接Telegram，等待下一个周期...")
            await asyncio.sleep(MONITOR_INTERVAL)
            continue
        
        try:
            total_processed = 0
            total_sent = 0
            
            # 处理每个API配置
            for api_index, api_cfg in enumerate(API_CONFIGS):
                # 如果API2被禁用且当前是API2则跳过
                if api_index == 1 and not ENABLE_API2:
                    continue
                
                # 处理每个频道
                for channel_url in CHANNEL_URLS:
                    processed, sent = await process_channel_for_api(client, channel_url, api_cfg, api_index)
                    total_processed += processed
                    total_sent += sent
            
            print(f"\n🔚 监控周期完成")
            print(f"总处理消息: {total_processed} | 总发送链接: {total_sent}")
            
        except Exception as e:
            print(f"监控过程中发生错误: {e}")
        finally:
            await client.disconnect()
        
        print(f"\n⏳ 等待 {MONITOR_INTERVAL} 秒后开始下一次监控...")
        await asyncio.sleep(MONITOR_INTERVAL)

if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 设置事件循环策略（Windows系统需要）
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行监控
    try:
        asyncio.run(continuous_monitoring())
    except KeyboardInterrupt:
        print("\n监控已停