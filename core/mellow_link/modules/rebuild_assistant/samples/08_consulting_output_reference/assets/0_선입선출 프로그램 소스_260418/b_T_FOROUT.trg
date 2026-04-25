CREATE OR REPLACE --11
trigger t_FOROUT -- 외화출금
before insert or delete on TN_FOROUT
for each row
declare
   wsys_date varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
begin
   if inserting then --- 호출 : 전입선출이력 생성 및 환차전표 생성
      p_FOROUT('A'          ,
              :new.BANK_CD  , :new.ACNT_NO   , :new.TR_DATE   , :new.TR_DATE_SEQ ,
              :new.ACCT_SEQ , :new.MNEY_UNIT , :new.OUTF_AMT  , :new.EXCH_RATE   ,
              :new.OUT_AMT  , :new.AC_DATE   , :new.AC_CHITNO , :new.UPD_EMP     ,
              :new.UPD_DATE );
   elsif deleting then
      p_FOROUT('D'
              :old.BANK_CD  , :old.ACNT_NO   , :old.TR_DATE   , :old.TR_DATE_SEQ ,
              :old.ACCT_SEQ , :old.MNEY_UNIT , :old.OUTF_AMT  , :old.EXCH_RATE   ,
              :old.OUT_AMT  , :old.AC_DATE   , :old.AC_CHITNO , :old.UPD_EMP     ,
              :old.UPD_DATE );
   end if;
end;
