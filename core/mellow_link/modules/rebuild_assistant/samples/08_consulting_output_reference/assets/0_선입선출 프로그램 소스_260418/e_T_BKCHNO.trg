---------- 14. T_BKCHNO
CREATE OR REPLACE
trigger T_BKCHNO -- 전표작성 interface
after update on TN_BKCHNO
for each row
declare
   wsys_date varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
begin -- 전표 생성
   p_BKCHNO (:new.CHK , :new.AC_DATE , :new.AC_CHITNO , :new.OCCR_PART ,
             :new.ACNT_DIV , :new.DEPT_CD , :new.INVOICE_NO , :new.TR_DATE ,
             :new.TR_DATE_SEQ, :new.CHIT_RMK , :new.INP_DATE , :new.UPD_DATE );
end;