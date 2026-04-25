CREATE OR REPLACE  --10
-- ---------------------------------------------------------
trigger t_FOROUT_B -- 외화출금시 환차전표번호 생성
before insert on TN_FOROUT
for each row
declare
   wsys_date   varchar2(14) := to_char(sysdate, 'yyyymmddhh24miss');
   w_CHITNO      number(04) := 0;
   w_CNTT        number(04) := 0;
   w_OCCR_PART varchar2(08) := '환차';
   w_CHIT_RMK  varchar2(200) := '외화출금 환차전표';
begin
   begin
      select max(AC_CHITNO)
         into w_CHITNO
         from TN_BKCHNO
      where ac_date = :new.AC_DATE;
   end;

   <<next_ins>>
   w_CHITNO := nvl(w_CHITNO, 0) + 1;

   if w_CHITNO > 9999 then
      Raise_Application_Error(-20001, '전표번호 자릿수 초과!!');
   end if;

   begin
      select count(*)
         into w_CNTT
         from TN_BKCHNO
      where ac_date = :new.AC_DATE
        and ac_chitno = w_CHITNO;
   end;

   if w_CNTT = 0 then
      begin
         insert into TN_BKCHNO
                    (ac_date    , ac_chitno , chk         , occr_part ,
                     invoice_no , TR_DATE   , TR_DATE_SEQ , CHIT_RMK  ,
                     inp_date   , upd_date )
             values (:new.AC_DATE , w_CHITNO     , '0'             , w_OCCR_PART ,
                     :new.ACCT_SEQ, :new.TR_DATE , :new.TR_DATE_SEQ, w_CHIT_RMK  ,
                     wsys_date , wsys_date );
      exception when dup_val_on_index then
                goto next_ins;
      end;
   else
      goto next_ins;
   end if;

   :new.AC_CHITNO := w_CHITNO;
end; 