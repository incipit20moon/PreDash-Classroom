"""Official monthly HS/country export signal. Never proxy a company's sales."""
import os,re
from datetime import datetime,date
from math import isfinite
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import requests

class CustomsError(ValueError):pass

def month_index(value):
    try:
        parsed=datetime.strptime(value,'%Y%m')
        if parsed.strftime('%Y%m')!=value:raise ValueError
        return parsed.year*12+parsed.month-1
    except (ValueError,TypeError):raise CustomsError('년월은 YYYYMM 형식으로 입력하세요.') from None

def month_text(index):return f'{index//12:04d}{index%12+1:02d}'

def parse_rows(content,hs,country,start,end):
    if len(content)>2_000_000 or b'<!DOCTYPE' in content.upper():raise CustomsError('수출 통계 응답을 안전하게 확인하지 못했습니다.')
    try:root=ET.fromstring(content)
    except ET.ParseError:raise CustomsError('수출 통계 XML 응답을 확인하지 못했습니다.') from None
    if root.findtext('.//resultCode')!='00':raise CustomsError('관세청 조회 실패 · 해당 API 활용 승인과 키를 확인하세요.')
    result={}
    items=root.findall('.//item')
    for row in items:
        period=(row.findtext('year') or '').strip()
        if period in ('총계','합계'):continue
        try:
            month=period.replace('.','').replace('-','');idx=month_index(month)
            if not start<=idx<=end:raise ValueError
            if (row.findtext('hsCd') or '').strip()!=hs or (row.findtext('statCd') or '').strip()!=country:raise ValueError
            amount=float((row.findtext('expDlr') or '').replace(',',''))
            if not isfinite(amount) or amount<0:raise ValueError
        except (ValueError,CustomsError):raise CustomsError('수출 통계의 기간·HS코드·국가·금액을 확인하지 못했습니다.') from None
        if idx in result:raise CustomsError('같은 월의 수출 통계가 중복돼 합산을 보류합니다.')
        result[idx]=amount
    total=root.findtext('.//totalCount')
    if total and total.isdigit() and int(total)>len(items):raise CustomsError('수출 통계 일부 페이지가 누락돼 집계를 보류합니다.')
    return result

def summarize(values):
    result=[]
    for index,amount in sorted(values.items()):
        previous=values.get(index-12)
        window=[values.get(i) for i in range(index-2,index+1)]
        result.append({'month':month_text(index),'export_usd':amount,
                       'yoy_pct':(amount/previous-1)*100 if previous is not None and previous>0 else None,
                       'ma3_usd':sum(window)/3 if all(v is not None for v in window) else None})
    return result

def exports(hs,country,end_month,today=None,key=None):
    if not re.fullmatch(r'(?:\d{2}|\d{4}|\d{6}|\d{10})',hs):raise CustomsError('HS코드는 숫자 2·4·6·10자리입니다. 제품 분석에는 세부코드를 권장합니다.')
    if not re.fullmatch(r'[A-Z]{2}',country):raise CustomsError('국가는 US처럼 영문 대문자 2자리로 입력하세요.')
    end=month_index(end_month);today=today or date.today()
    if end>=today.year*12+today.month-1:raise CustomsError('진행 중인 이번 달 이전의 종료월을 선택하세요.')
    key=(key if key is not None else os.getenv('CUSTOMS_API_KEY','')).strip()
    if not key:raise CustomsError('CUSTOMS_API_KEY와 관세청 품목별 국가별 수출입실적 API 활용 승인을 확인하세요.')
    values={}
    for start,stop in ((end-23,end-12),(end-11,end)):
        try:
            response=requests.get('https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList',
                params={'serviceKey':unquote(key),'strtYymm':month_text(start),'endYymm':month_text(stop),'hsSgn':hs,'cntyCd':country},timeout=(5,25))
            response.raise_for_status()
        except requests.RequestException:raise CustomsError('관세청 연결에 실패했습니다. 잠시 후 다시 조회하세요.') from None
        values.update(parse_rows(response.content,hs,country,start,stop))
    if not values:raise CustomsError('조회된 월별 수출 자료가 없습니다. HS코드와 국가를 확인하세요.')
    return {'hs':hs,'country':country,'from':month_text(end-23),'to':end_month,'rows':summarize(values),
            'unit':'USD','source':'관세청 품목별 국가별 수출입실적','fetched':datetime.now().isoformat(timespec='seconds')}

