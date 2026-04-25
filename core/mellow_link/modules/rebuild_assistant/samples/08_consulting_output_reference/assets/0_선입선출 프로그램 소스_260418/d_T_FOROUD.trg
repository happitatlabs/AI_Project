trigger t_FOROUD -- 13 선입선출이력
before insert or update or delete on TN_FOROUD
for each row
declare
   wsys_date     varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
   w_BANK_CD     varchar2(07) := '';
   w_ACNT_NO     varchar2(20) := '';
   w_TR_DATE     varchar2(08) := '';
   w_TR_DATE_SEQ   number(10) := 0;
   w_ACCT_SEQ0   varchar2(50) := '';
   w_TR_DATE0    varchar2(08) := '';
   w_TR_DATE_SEQ0  number(10) := 0;
   w_OUTF_AMT      number(15,2) := 0; -- 외화출금LOT
   w_OUT_AMT       number(15) := 0; -- 출금환산LOT
   w_OUT_AMT0      number(15) := 0; -- 출고원금LOT
   w_GAP_AMT       number(15) := 0; -- 환차 LOT
begin
   if inserting then
      w_BANK_CD      := :new.BANK_CD ;
      w_ACNT_NO      := :new.ACNT_NO ;
      w_TR_DATE      := :new.TR_DATE ;
      w_TR_DATE_SEQ  := :new.TR_DATE_SEQ ;
      w_ACCT_SEQ0    := :new.ACCT_SEQ0 ;
      w_TR_DATE0     := :new.TR_DATE0 ;
      w_TR_DATE_SEQ0 := :new.TR_DATE_SEQ0 ;
      w_OUTF_AMT     := nvl(:new.OUTF_AMT,0);
      w_OUT_AMT      := nvl(:new.OUT_AMT,0) ;
      w_OUT_AMT0     := nvl(:new.OUT_AMT0,0);
      w_GAP_AMT      := nvl(:new.GAP_AMT,0) ;
   elsif updating then
      w_BANK_CD      := :new.BANK_CD ;
      w_ACNT_NO      := :new.ACNT_NO ;
      w_TR_DATE      := :new.TR_DATE ;
      w_TR_DATE_SEQ  := :new.TR_DATE_SEQ ;
      w_ACCT_SEQ0    := :new.ACCT_SEQ0 ;
      w_TR_DATE0     := :new.TR_DATE0 ;
      w_TR_DATE_SEQ0 := :new.TR_DATE_SEQ0 ;
      w_OUTF_AMT     := nvl(:new.OUTF_AMT,0) - nvl(:old.OUTF_AMT,0);
      w_OUT_AMT      := nvl(:new.OUT_AMT,0) - nvl(:old.OUT_AMT,0) ;
      w_OUT_AMT0     := nvl(:new.OUT_AMT0,0) - nvl(:old.OUT_AMT0,0);
      w_GAP_AMT      := nvl(:new.GAP_AMT,0) - nvl(:old.GAP_AMT,0) ;
   elsif deleting then
      w_BANK_CD      := :old.BANK_CD ;
      w_ACNT_NO      := :old.ACNT_NO ;
      w_TR_DATE      := :old.TR_DATE ;
      w_TR_DATE_SEQ  := :old.TR_DATE_SEQ ;
      w_ACCT_SEQ0    := :old.ACCT_SEQ0 ;
      w_TR_DATE0     := :old.TR_DATE0 ;
      w_TR_DATE_SEQ0 := :old.TR_DATE_SEQ0 ;
      w_OUTF_AMT     := nvl(:old.OUTF_AMT,0) * -1;
      w_OUT_AMT      := nvl(:old.OUT_AMT,0) * -1;
      w_OUT_AMT0     := nvl(:old.OUT_AMT0,0) * -1;
      w_GAP_AMT      := nvl(:old.GAP_AMT,0) * -1;
   end if;
   -- 출금
   begin
      update TN_FOROUT set
             OUT_SUM = nvl(OUT_SUM, 0) + w_OUT_AMT0, -- 상세집계(출고원금)
             GAP_SUM = nvl(GAP_SUM, 0) + w_GAP_AMT -- 상세집계(환차)
      where BANK_CD     = w_BANK_CD
        and ACNT_NO     = w_ACNT_NO
        and TR_DATE     = w_TR_DATE
        and TR_DATE_SEQ = w_TR_DATE_SEQ;
   end;
   -- 입금
   begin
      update TN_FORINS set
             O_FSUM  = nvl(O_FSUM, 0)  + w_OUTF_AMT, -- 외화출금누계 = sum(외화출금Lot)
             O_SUM   = nvl(O_SUM, 0)   + w_OUT_AMT , -- 출금환산누계 = sum(출금환산Lot)
             GAP_AMT = nvl(GAP_AMT, 0) + w_GAP_AMT
      where ACCT_SEQ    = w_ACCT_SEQ0
        and TR_DATE     = w_TR_DATE0
        and TR_DATE_SEQ = w_TR_DATE_SEQ0;
   end;
end;
   
   
