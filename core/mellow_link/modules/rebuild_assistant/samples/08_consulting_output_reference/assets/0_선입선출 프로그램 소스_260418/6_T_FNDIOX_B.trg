CREATE OR REPLACE--6
trigger t_FNDIOX_B -- 입금(가수금) 전표번호 생성
before insert or update on IB_ACCTALL_TR_DD_ADD
for each row
declare
   sysdt        varchar2(14) := to_char(sysdate, 'YYYYMMDDHH24MISS');
   W_CNTT         number(05) := 0 ;
   W_CHIT_NO      number(05) := 0 ;
   W_CHIT_RMK   varchar2(200) := '가수금 입금';
   W_OCCR_PART  varchar2(08) := '공통' ;
   wPAY_UNIT_CD VARCHAR2(03) := '' ;
   wPAY_DIV     VARCHAR2(03) := '' ;
   wPAY_DATE    VARCHAR2(08) := '' ;
   wPAY_CHITNO    number(05) := 0 ;
   wPAY_HANG      number(04) := 0 ;
   wAPP_DATE    VARCHAR2(08) := '' ;
   wAPP_NO        number(05) := 0 ;
   wHANG          number(04) := 0 ;

begin
   IF INSERTING THEN
      --- 0. 출금시 출금의뢰(payord) 거래내역 update
      IF :new.TR_IPJI_GBN = '2' THEN --- 출금 : 결과가 기록되지 않은 건
         BEGIN
            SELECT a.ACNT_UNIT_CD, a.ACNT_DIV, a.AC_DATE, a.AC_CHITNO, a.AC_HANG,
                   a.APP_DATE, a.APP_NO, a.HANG
                into wPAY_UNIT_CD, wPAY_DIV, wPAY_DATE, wPAY_CHITNO, wPAY_HANG,
                     wAPP_DATE, wAPP_NO, wHANG
                from TN_PAY_ORDER_DTL /*'payord'*/ a
            where a.out_acnt_nox = :new.acnt_no
              and a.pay_date = :new.tr_date
              and a.chit_amt = :new.tr_amt
              and replace(to_single_byte(a.cust_acnm), ' ', '') = replace(:new.naeyong, ' ', '')
              and a.acct_seq is null
and rownum = 1;
exception when no_data_found then
BEGIN
SELECT a.ACNT_UNIT_CD, a.ACNT_DIV, a.AC_DATE, a.AC_CHITNO, a.AC_HANG,
a.APP_DATE, a.APP_NO, a.HANG
into wPAY_UNIT_CD, wPAY_DIV, wPAY_DATE, wPAY_CHITNO, wPAY_HANG,
wAPP_DATE, wAPP_NO, wHANG
from TN_PAY_ORDER_DTL /*'payord'*/ a
where a.out_acnt_nox = :new.acnt_no
and a.pay_date = :new.tr_date
and a.chit_amt = :new.tr_amt
and a.acct_seq is null
and rownum = 1;
exception when no_data_found then wPAY_UNIT_CD := '';
END;
END;

if wPAY_UNIT_CD is not null then
begin
update TN_PAY_ORDER_DTL set
acct_seq = :new.acct_seq,
tr_date = :new.tr_date,
tr_date_seq = :new.tr_date_seq
where ACNT_UNIT_CD = wPAY_UNIT_CD
and ACNT_DIV = wPAY_DIV
and AC_DATE = wPAY_DATE
and AC_CHITNO = wPAY_CHITNO
and AC_HANG = wPAY_HANG;
end;
:new.PAY_UNIT_CD := wPAY_UNIT_CD;
:new.PAY_DIV := wPAY_DIV;
:new.PAY_DATE := wPAY_DATE;
:new.PAY_CHITNO := wPAY_CHITNO;
:new.PAY_HANG := wPAY_HANG;
end if;
END IF;
END IF;

--- 입금
IF (:new.tr_ipji_gbn = '1') then --- 1. 입금일 경우 출금의뢰가 있었는지 확인해서 없을 경우 "가수금처리"
if nvl(:new.naeyong, ' ') like '한국정책방송원공사%' then ---공사 입금의뢰 제외
begin
select count(*)
into W_CNTT
from FNDICK a --- 출금의뢰
where a.tran_dt = :new.tr_date --- 일자
and replace(a.tran_ip_acct_nb, '-', '') = :new.acct_no --- 계좌
and a.tran_amt_req = :new.tr_amt; --- 금액
end;
end if;

if nvl(W_CNTT, 0) <> 0 then --- 출금의뢰가 있을 경우 PASS
goto end_x;
end if;
end if;

if (inserting) OR (updating and nvl(:new.AC_CHITNO, 0) = 0) Then
if (:new.tr_ipji_gbn = '1') then --- 입금 (가수금 전표번호 생성)
:new.AC_DATE := :new.TR_DATE;
-- 회계전표번호 - 가수금 전표번호 생성
begin
select max(AC_CHITNO)
into w_CHIT_NO
from TN_BKCHNO
where ac_date = :new.TR_DATE;
end;
W_CHIT_NO := nvl(W_CHIT_NO, 0) + 1;
begin
insert INTO TN_BKCHNO
(ac_date, ac_chitno, CHK, OCCR_PART,
INVOICE_NO, TR_DATE, TR_DATE_SEQ, CHIT_RMK,
INP_DATE)
values (:new.TR_DATE, w_CHIT_NO, '0', w_OCCR_PART,
:new.ACCT_SEQ, :new.TR_DATE, :new.TR_DATE_SEQ, W_CHIT_RMK,
sysdt);
exception when dup_val_on_index then null;
end;
:new.AC_CHITNO := w_CHIT_NO;
end if;
end if;
<<end_x>>
null;
ELSE
--- updating
if updating then
--- 0. 출금시 출금의뢰(payord) 거래내역 update
IF :new.TR_IPJI_GBN = '2' and :old.PAY_UNIT_CD is null THEN --- 출금결과가 기록되지 않은 건
BEGIN
SELECT a.ACNT_UNIT_CD, a.ACNT_DIV, a.AC_DATE, a.AC_CHITNO, a.AC_HANG,
a.APP_DATE, a.APP_NO, a.HANG
into wPAY_UNIT_CD, wPAY_DIV, wPAY_DATE, wPAY_CHITNO, wPAY_HANG,
wAPP_DATE, wAPP_NO, wHANG
from TN_PAY_ORDER_DTL /*'payord'*/ a
where a.out_acnt_nox = :new.acnt_no
and a.pay_date = :new.tr_date
and a.chit_amt = :new.tr_amt
and replace(to_single_byte(a.cust_acnm), ' ', '') = replace(:new.naeyong, ' ', '')
and a.acct_seq is null
and rownum = 1;
exception when no_data_found then
BEGIN
SELECT a.ACNT_UNIT_CD, a.ACNT_DIV, a.AC_DATE, a.AC_CHITNO, a.AC_HANG,
a.APP_DATE, a.APP_NO, a.HANG
into wPAY_UNIT_CD, wPAY_DIV, wPAY_DATE, wPAY_CHITNO, wPAY_HANG,
wAPP_DATE, wAPP_NO, wHANG
from TN_PAY_ORDER_DTL /*'payord'*/ a
where a.out_acnt_nox = :new.acnt_no
and a.pay_date = :new.tr_date
and a.chit_amt = :new.tr_amt
and a.acct_seq is null
and rownum = 1;
exception when no_data_found then wPAY_UNIT_CD := '';
END;
END;

if wPAY_UNIT_CD is not null then
begin
update TN_PAY_ORDER_DTL set
acct_seq = :new.acct_seq,
tr_date = :new.tr_date,
tr_date_seq = :new.tr_date_seq
where ACNT_UNIT_CD = wPAY_UNIT_CD
and ACNT_DIV = wPAY_DIV
and AC_DATE = wPAY_DATE
and AC_CHITNO = wPAY_CHITNO
and AC_HANG = wPAY_HANG;
end;
:new.PAY_UNIT_CD := wPAY_UNIT_CD;
:new.PAY_DIV := wPAY_DIV;
:new.PAY_DATE := wPAY_DATE;
:new.PAY_CHITNO := wPAY_CHITNO;
:new.PAY_HANG := wPAY_HANG;
end if;
END IF;

-- 회계전표번호
begin
select max(AC_CHITNO)
into w_CHIT_NO
from TN_BKCHNO
where ac_date = :new.TR_DATE;
end;
W_CHIT_NO := nvl(W_CHIT_NO, 0) + 1;
begin
insert INTO TN_BKCHNO
(ac_date, ac_chitno, CHK, OCCR_PART,
INVOICE_NO, TR_DATE, TR_DATE_SEQ, CHIT_RMK,
INP_DATE)
values (:new.TR_DATE, w_CHIT_NO, '0', w_OCCR_PART,
:new.ACCT_SEQ, :new.TR_DATE, :new.TR_DATE_SEQ, W_CHIT_RMK,
sysdt);
exception when dup_val_on_index then null;
end;
:new.ac_date := :new.tr_date;
:new.AC_CHITNO := w_CHIT_NO;
end if;
<<end_p>>
null;
END IF;
end;