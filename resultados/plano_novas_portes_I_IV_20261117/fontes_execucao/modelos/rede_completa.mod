# Extensao especializada do plano APS completo: vinculacao primaria fixada.
# Modelo novo: atencao programada. Nao substitui model.py nem hc.mod.
# I: pontos; U: UBS; S/T: ofertas secundaria/terciaria; K: ambulatorial/hospitalar.
set I;
set U;
set S;
set T;
set K;
set F := S union T;
param POP{I}, >0;
param ESF{U}, >=0;
param MAXE{U}, >=0;
param HAB, >0, default 3000;
param VINC{I,U}, >=0;
param D2{I,K}, >=0; param D3{I,K}, >=0;
param R, >=0, <=1; # Fracao da demanda terciaria que passa pela secundaria.
param AMB{F}, >=0; param LEITO{F}, >=0;
param HOSPITAL{F}, binary; param TMP2, >0; param TMP3, >0;
param DU{I,U}, >=0; param US{U,S}, >=0;
param UT{U,T}, >=0; param ST{S,T}, >=0;
param fase, integer; param falta_max, default 1e9; param equipes_max, default 1e9;
param N2{k in K}:=sum{i in I}D2[i,k];
param N3{k in K}:=sum{i in I}D3[i,k];
param NP:=sum{i in I}POP[i];

# x divide a populacao de um ponto entre UBS, como a alocacao multipla da aula.
var x{I,U}, >=0;
var novas{U}, integer, >=0;
# f: termina na secundaria; d: terciaria direta; v: terciaria via secundaria.
var f{I,U,K,S}, >=0;
var d{I,U,K,T}, >=0;
var v{I,U,K,S,T}, >=0;
var nf{I,U,K}, >=0; var nd{I,U,K}, >=0; var nv{I,U,K}, >=0;

# Cada via nao atendida falta nos dois niveis. Nao ha atendimento parcial da cadeia.
var falta, >=0;
var viagem, >=0;
s.t. medida_falta: falta =
 sum{i in I,u in U,k in K}(nf[i,u,k]+nv[i,u,k])/N2[k]
 +sum{i in I,u in U,k in K}(nd[i,u,k]+nv[i,u,k])/N3[k];
s.t. medida_viagem: viagem =
 sum{i in I,u in U}POP[i]*DU[i,u]*x[i,u]/NP
 +sum{i in I,u in U,k in K,s in S}(DU[i,u]+US[u,s])*f[i,u,k,s]/N2[k]
 +sum{i in I,u in U,k in K,t in T}(DU[i,u]+UT[u,t])*d[i,u,k,t]/N3[k]
 +sum{i in I,u in U,k in K,s in S,t in T}
 ((DU[i,u]+US[u,s])/N2[k]+ST[s,t]/N3[k])*v[i,u,k,s,t];
# Na abordagem sequencial, a APS esta fixa e novas[u]=0.
# O integrador resolve fase 1 (falta) e fase 3 (deslocamento); fase 2 nao e utilizada.
minimize objetivo: if fase=1 then falta else if fase=2 then sum{u in U}novas[u] else viagem;
s.t. preserva_falta: falta<=falta_max;
s.t. preserva_equipes: sum{u in U}novas[u]<=equipes_max;
s.t. fixa_plano_aps{i in I,u in U}: x[i,u]=VINC[i,u];
s.t. sem_redimensionar_aps{u in U}: novas[u]=0;
s.t. vinculo{i in I}:sum{u in U}x[i,u]=1;
s.t. capacidade_ubs{u in U}:sum{i in I}POP[i]*x[i,u]<=HAB*(ESF[u]+novas[u]);
s.t. teto_equipes{u in U}:ESF[u]+novas[u]<=MAXE[u];
s.t. minimo_equipes:sum{u in U}novas[u]>=ceil(sum{i in I}POP[i]/HAB)-sum{u in U}ESF[u];

# A parcela via secundaria JA pertence a D2; nao gera demanda adicional.
s.t. termina{i in I,u in U,k in K}:
 sum{s in S}f[i,u,k,s]+nf[i,u,k]=(D2[i,k]-R*D3[i,k])*x[i,u];
s.t. direto{i in I,u in U,k in K}:
 sum{t in T}d[i,u,k,t]+nd[i,u,k]=(1-R)*D3[i,k]*x[i,u];
s.t. via{i in I,u in U,k in K}:
 sum{s in S,t in T}v[i,u,k,s,t]+nv[i,u,k]=R*D3[i,k]*x[i,u];

# Um unico teto ambulatorial por local, mesmo quando oferece dois niveis.
s.t. capacidade_amb{a in F}:
 sum{i in I,u in U,s in S:s=a}f[i,u,'AMB',s]
 +sum{i in I,u in U,t in T:t=a}d[i,u,'AMB',t]
 +sum{i in I,u in U,s in S,t in T}((if s=a then 1 else 0)+(if t=a then 1 else 0))*v[i,u,'AMB',s,t]<=AMB[a];
# Se a cadeia ocorre no mesmo local, os dois atendimentos consomem capacidade.
s.t. capacidade_leitos{a in F}:
 TMP2*(sum{i in I,u in U,s in S:s=a}f[i,u,'HOSP',s]
 +sum{i in I,u in U,s in S,t in T:s=a}v[i,u,'HOSP',s,t])
 +TMP3*(sum{i in I,u in U,t in T:t=a}d[i,u,'HOSP',t]
 +sum{i in I,u in U,s in S,t in T:t=a}v[i,u,'HOSP',s,t])<=LEITO[a];
s.t. apenas_hospital2{i in I,u in U,s in S}:
 f[i,u,'HOSP',s]+sum{t in T}v[i,u,'HOSP',s,t]<=N2['HOSP']*HOSPITAL[s];
s.t. apenas_hospital3{i in I,u in U,t in T}:
 d[i,u,'HOSP',t]+sum{s in S}v[i,u,'HOSP',s,t]<=N3['HOSP']*HOSPITAL[t];
solve;
printf "RESUMO;falta;%.14g\n",falta;
printf "RESUMO;equipes;%.14g\n",sum{u in U}novas[u];
printf "RESUMO;viagem;%.14g\n",viagem;
printf{u in U} "UBS;%s;%.14g;%.14g;%.14g\n",u,novas[u],sum{i in I}POP[i]*x[i,u],HAB*(ESF[u]+novas[u]);
printf{i in I,u in U:x[i,u]>1e-9} "X;%s;%s;%.14g\n",i,u,x[i,u];
printf{i in I,u in U,k in K,s in S:f[i,u,k,s]>1e-8}
 "F;%s;%s;%s;%s;%.14g\n",i,u,k,s,f[i,u,k,s];
printf{i in I,u in U,k in K,t in T:d[i,u,k,t]>1e-8}
 "D;%s;%s;%s;%s;%.14g\n",i,u,k,t,d[i,u,k,t];
printf{i in I,u in U,k in K,s in S,t in T:v[i,u,k,s,t]>1e-8}
 "V;%s;%s;%s;%s;%s;%.14g\n",i,u,k,s,t,v[i,u,k,s,t];
printf{i in I,u in U,k in K:nf[i,u,k]+nd[i,u,k]+nv[i,u,k]>1e-8}
 "N;%s;%s;%s;%.14g;%.14g;%.14g\n",i,u,k,nf[i,u,k],nd[i,u,k],nv[i,u,k];
end;
