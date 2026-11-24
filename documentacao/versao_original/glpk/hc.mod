###############################################################################
# Health Care Facility Location Problem: considering fixed facilities,
# choose intermediate facilities according to a criterion that improves
# service quality. Consider health care teams.
###############################################################################
# glpsol -m hc.mod -d hc.dat --cuts

set I;                      # The set of demand points.
set K;                      # Health care levels (PHC, SHC, THC)
set P;                      # Types of patients (chronic or acute)
set E{K};                   # Health care team from level k
set EL{K};                  # EXISTING health care units on three levels
set CL{K};                  # CANDIDATE health care LOCATIONS on three levels
set L{k in K} := EL[k] union CL[k];

###############################################
param CE1{c in E[1]};       # Team cost K1 ($/month)
param CE2{c in E[2]};       # Team cost K2 ($/month)
param CE3{c in E[3]};       # Team cost K3 ($/month)

param D1{I,L[1]};           # The travel time between i and level-1 PCF.   (min)
param D2{L[1],L[2]};        # The travel time between candidate L1 and L2. (min)
param D3{L[2],L[3]};        # The travel time between candidate L2 and L3. (min)

param TC1{I,L[1]};          # Travel cost/pat p, from demand point i to L1 ($/min)
param TC2{L[1],L[2]};       # Travel cost/pat p, from L1 to L2             ($/min)
param TC3{L[2],L[3]};       # Travel cost/pat p, from L2 to L3             ($/min)

param VC1{P,L[1]};          # Variable cost of PHC j / pop h ($/pop)
param VC2{P,L[2]};          # Variable cost of SHC j / pop h ($/pop)
param VC3{P,L[3]};          # Variable cost of THC j / pop h ($/pop)

param FC1{L[1]};            # Fixed cost per period for operating PHC j ($/month)
param FC2{L[2]};            # Fixed cost per period for operating SHC j ($/month)
param FC3{L[3]};            # Fixed cost per period for operating THC j ($/month)

param W{I,P};               # The population size of type p at demand point i (pop)

param MS1{E[1]};            # Ministry of Health: requirements for PHC (prof/pop)
param MS2{E[2]};            # Ministry of Health: requirements for SHC (prof/pop)
param MS3{E[3]};            # Ministry of Health: requirements for THC (prof/pop)

param CNES1{E[1],L[1]};     # Health professional teams PHC at location L1 (prof)
param CNES2{E[2],L[2]};     # Health professional teams SHC at location L2 (prof)
param CNES3{E[3],L[3]};     # Health professional teams THC at location L3 (prof)

# Service operating capacity at facility j
param C1{P,L[1]};           # The capacity of a level-1 PCF in K. (pop)
param C2{L[2]};             # The capacity of a level-2 PCF in J. (pop)
param C3{L[3]};             # The capacity of a level-3 PCF in J. (pop)

param U{K};                 # The number of UNITS level-k to be established. (unit)

param O1{L[1]};             # The proportion of patients in a L-1 to a L-2 PCF. (%)
param O2{L[2]};             # The proportion of patients in a L-2 to a L-3 PCF. (%)

###############################################
var y{i in I, j1 in L[1]}, >=0, binary;  # 1, if pop i is ASSIGNED to L-1 PCF j1 (1) or not (0)
var y1{j1 in L[1]}, >=0, binary;         # 1, if a L-1 PCF is used (1) or not (0)
var y2{j2 in L[2]}, >=0, binary;         # 1, if a L-2 SCF is used (1) or not (0)
var y3{j3 in L[3]}, >=0, binary;         # 1, if a L-3 TCF is used (1) or not (0)

var u1{P, i in I, j1 in L[1]}, >=0;      # The flow p between demand point i and L1 (pop)
var u2{j1 in L[1], j2 in L[2]}, >=0;     # The flow between L1 and L2               (pop)
var u3{j2 in L[2], j3 in L[3]}, >=0;     # The flow between L2 and L3               (pop)

var l1{E[1],L[1]};                       # Lack (or excess) of professional e on location L1 (prof)
var l2{E[2],L[2]};                       # Lack (or excess) of professional e on location L2 (prof)
var l3{E[3],L[3]};                       # Lack (or excess) of professional e on location L3 (prof)

###############################################
# Minimizes social and business costs:
# the total demand-weighted travel distance (or time) +
# the total fixed costs of operating the facilities
# (related to health care teams for each location) +
# the total variable costs / patient of operating the facilities.

minimize Total_Costs:
    # Patient transportation cost
      sum{p in P, i in I, j1 in L[1]}D1[i,j1]*TC1[i,j1]*u1[p,i,j1]
    + sum{j1 in L[1], j2 in L[2]}D2[j1,j2]*TC2[j1,j2]*u2[j1,j2]
    + sum{j2 in L[2], j3 in L[3]}D3[j2,j3]*TC3[j2,j3]*u3[j2,j3]
    # Cost of existing unit (including staff)
    + sum{j1 in EL[1]}FC1[j1]*y1[j1]
    + sum{j2 in EL[2]}FC2[j2]*y2[j2]
    + sum{j3 in EL[3]}FC3[j3]*y3[j3]
    # New unit cost
    + sum{j1 in CL[1]}FC1[j1]*y1[j1]
    + sum{j2 in CL[2]}FC2[j2]*y2[j2]
    + sum{j3 in CL[3]}FC3[j3]*y3[j3]
    # Cost of new staff
    + sum{j1 in CL[1], c1 in E[1]}CE1[c1]*y1[j1]
    + sum{j2 in CL[2], c2 in E[2]}CE2[c2]*y2[j2]
    + sum{j3 in CL[3], c3 in E[3]}CE3[c3]*y3[j3]
    # Variable cost per patient
    + sum{p in P, i in I, j1 in L[1]}D1[i,j1]*VC1[p,j1]*u1[p,i,j1]
    + sum{p in P, j1 in L[1], j2 in L[2]}D2[j1,j2]*VC2[p,j2]*u2[j1,j2]
    + sum{p in P, j2 in L[2], j3 in L[3]}D3[j2,j3]*VC3[p,j3]*u3[j2,j3];

# Fix variables of EXISTING location
s.t. F1{j1 in EL[1]}:y1[j1] = 1;
s.t. F2{j2 in EL[2]}:y2[j2] = 1;
s.t. F3{j3 in EL[3]}:y3[j3] = 1;

# Entire population at each demand point i must be assigned
# to (existing and candidate) location L1
# (pop) = (pop)
s.t. R0{i in I, j1 in L[1]}: sum{p in P}W[i,p]*y[i,j1] = sum{p in P}u1[p,i,j1];
s.t. R0a{i in I}: sum{j1 in L[1]}y[i,j1] = 1;

# Flow balance from PHC > SHC > THC
# (pop) = (pop)
s.t. R1{j1 in L[1]}: sum{j2 in L[2]}u2[j1,j2] = O1[j1]*sum{p in P,i in I}u1[p,i,j1];
s.t. R2{j2 in L[2]}: sum{j3 in L[3]}u3[j2,j3] = O2[j2]*sum{j1 in L[1]}u2[j1,j2];

# Team of existing
# (pop)*(prof/pop) - (prof) = (prof)
s.t. R3e{j1 in EL[1], e1 in E[1]}: sum{p in P, i in I}u1[p,i,j1]*MS1[e1] - l1[e1,j1] = CNES1[e1,j1];
s.t. R4e{j2 in EL[2], e2 in E[2]}: sum{j1 in L[1]}u2[j1,j2]*MS2[e2] - l2[e2,j2] = CNES2[e2,j2];
s.t. R5e{j3 in EL[3], e3 in E[3]}: sum{j2 in L[2]}u3[j2,j3]*MS3[e3] - l3[e3,j3] = CNES3[e3,j3];

# New team?
# (prof) = (prof)
s.t. R3c{j1 in CL[1], e1 in E[1]}: sum{p in P, i in I}u1[p,i,j1]*MS1[e1] = l1[e1,j1];
s.t. R4c{j2 in CL[2], e2 in E[2]}: sum{j1 in L[1]}u2[j1,j2]*MS2[e2] = l2[e2,j2];
s.t. R5c{j3 in CL[3], e3 in E[3]}: sum{j2 in L[2]}u3[j2,j3]*MS3[e3] = l3[e3,j3];

# Capacity of existing (patients)
# (pop) = (pop)
s.t. R6e{j1 in EL[1], p in P}: sum{i in I}u1[p,i,j1] <= C1[p,j1];
s.t. R7e{j2 in EL[2]}: sum{j1 in L[1]}u2[j1,j2] <= C2[j2];
s.t. R8e{j3 in EL[3]}: sum{j2 in L[2]}u3[j2,j3] <= C3[j3];

# Activation of new units (?)
# (pop) = (pop)
s.t. R6c{j1 in CL[1], p in P}: sum{i in I}u1[p,i,j1] <= C1[p,j1]*y1[j1];
s.t. R7c{j2 in CL[2]}: sum{j1 in L[1]}u2[j1,j2] <= C2[j2]*y2[j2];
s.t. R8c{j3 in CL[3]}: sum{j2 in L[2]}u3[j2,j3] <= C3[j3]*y3[j3];

# The number of a level-k to be established.
# (units) = (units)
s.t. R9c:  sum{j1 in CL[1]}y1[j1] <= U[1];
s.t. R10c: sum{j2 in CL[2]}y2[j2] <= U[2];
s.t. R11c: sum{j3 in CL[3]}y3[j3] <= U[3];

solve;

###############################################################################
# REPORT
###############################################################################
printf "\n=======================================\n";
printf "Health Care Plan\n";
printf "=======================================\n";
printf "Logist cost:\t\t$%6.2f\n",
      sum{p in P, i in I, j1 in L[1]}D1[i,j1]*TC1[i,j1]*u1[p,i,j1]
    + sum{j1 in L[1], j2 in L[2]}D2[j1,j2]*TC2[j1,j2]*u2[j1,j2]
    + sum{j2 in L[2], j3 in L[3]}D3[j2,j3]*TC3[j2,j3]*u3[j2,j3];
printf "Fixed cost [E]:\t\t$%6.2f\n",
      sum{j1 in EL[1]}FC1[j1]*y1[j1]
    + sum{j2 in EL[2]}FC2[j2]*y2[j2]
    + sum{j3 in EL[3]}FC3[j3]*y3[j3];
printf "Fixed cost [C]:\t\t$%6.2f\n",
      sum{j1 in CL[1]}FC1[j1]*y1[j1]
    + sum{j2 in CL[2]}FC2[j2]*y2[j2]
    + sum{j3 in CL[3]}FC3[j3]*y3[j3];
printf "New team cost [C]:\t$%6.2f\n",
      sum{j1 in CL[1],c1 in E[1]}CE1[c1]*y1[j1]
    + sum{j2 in CL[2],c2 in E[2]}CE2[c2]*y2[j2]
    + sum{j3 in CL[3],c3 in E[3]}CE3[c3]*y3[j3];
printf "Variable Cost:\t\t$%6.2f\n",
      sum{p in P, i in I, j1 in L[1]}D1[i,j1]*VC1[p,j1]*u1[p,i,j1]
    + sum{p in P, j1 in L[1], j2 in L[2]}D2[j1,j2]*VC2[p,j2]*u2[j1,j2]
    + sum{p in P, j2 in L[2], j3 in L[3]}D3[j2,j3]*VC3[p,j3]*u3[j2,j3];
printf "=======================================\n";
printf "Total    Cost:\t\t$%6.2f\n", Total_Costs;
printf "=======================================\n";
printf "New Units:\tQty\tMax\tUse (%%)\n";
printf "=======================================\n";
printf "PHC     :\t%d\t%d\t%.2f%%\n",
    sum{j1 in CL[1]}y1[j1],
    U[1], ((sum{j1 in CL[1]}y1[j1])/(U[1]))*100;
printf "SHC     :\t%d\t%d\t%.2f%%\n",
    sum{j2 in CL[2]}y2[j2],
    U[2], ((sum{j2 in CL[2]}y2[j2])/(U[2]))*100;
printf "THC     :\t%d\t%d\t%.2f%%\n",
    sum{j3 in CL[3]}y3[j3],
    U[3], ((sum{j3 in CL[3]}y3[j3])/(U[3]))*100;
printf "=======================================\n";
printf "Municipality:\t Pop\t Flow\n";
printf "=======================================\n";
printf{i in I}: "[%-14s]: %d\t %d\n", i,
    sum{p in P}W[i,p],
    sum{p in P,j1 in L[1]}u1[p,i,j1];
printf "=======================================\n";
printf "Mun     > PHC   :(flow)\n";
printf "=======================================\n";
for{i in I}{
    printf"M[%-4d] > \t: %d\n", i, sum{p in P}W[i,p];
    for{j1 in L[1]: sum{p in P}u1[p,i,j1] > 0}{
        printf"\t> L[%-3d]: %d\n", j1, sum{p in P}u1[p,i,j1];
    }
}
printf "=======================================\n";
printf "PHC     > SHC   :(flow)\n";
printf "=======================================\n";
for{j1 in L[1]: sum{p in P,i in I}u1[p,i,j1] > 0}{
    printf"L[%-4d] > \t: %d\n", j1, O1[j1]*sum{p in P,i in I}u1[p,i,j1];
    for{j2 in L[2]: u2[j1,j2] > 0}{
        printf"\t> L[%-3d]: %d\n", j2, u2[j1,j2];
    }
}

printf "=======================================\n";
printf "SHC     > THC   :(flow)\n";
printf "=======================================\n";
for{j2 in L[2]: sum{j1 in L[1]}u2[j1,j2]>0}{
    printf "L[%-4d] > \t : %d\n", j2, O2[j2]*sum{j1 in L[1]}u2[j1,j2];
    for{j3 in L[3]: u3[j2,j3] > 0}{
        printf "\t> L[%-4d]: %d\n", j3, u3[j2,j3];
    }
}

printf "=======================================\n\n";
printf "=======================================\n";
printf "Health care team (Existing and New*)\n";
printf "=======================================\n";
printf "=======================================\n";
printf "PHC-Team CNES\tFlow\tLack/Excess\n";
printf "=======================================\n";
for{j1 in EL[1]: sum{p in P,i in I}u1[p,i,j1] > 0}{
    printf"L[%-2d]\n", j1;
    for{e1 in E[1]}{
        printf"  [%-s]: %.2f\t%.2f\t%.2f\n", e1, CNES1[e1,j1],
        sum{p in P, i in I}u1[p,i,j1]*MS1[e1],
        l1[e1,j1];
    }
}
for{j1 in CL[1]: sum{p in P,i in I}u1[p,i,j1] > 0}{
    printf"L[%-d*]\n", j1;
    for{e1 in E[1]}{
        printf"  [%-s]: \t%.2f\t%.2f\n", e1,
        sum{p in P, i in I}u1[p,i,j1]*MS1[e1],
        l1[e1,j1];
    }
}
printf "=======================================\n";
printf "SHC-Team CNES\tFlow\tLack/Excess\n";
printf "=======================================\n";
for{j2 in EL[2]: sum{j1 in L[1]}u2[j1,j2] > 0}{
    printf"L[%-2d]\n", j2;
    for{e2 in E[2]}{
        printf"  [%-s]: %.2f\t%.2f\t%.2f\n", e2, CNES2[e2,j2],
        sum{j1 in L[1]}u2[j1,j2]*MS2[e2],
        l2[e2,j2];
    }
}
for{j2 in CL[2]: sum{j1 in L[1]}u2[j1,j2] > 0}{
    printf"L[%-d*]\n", j2;
    for{e2 in E[2]: sum{j1 in L[1]}u2[j1,j2]>0}{
        printf"  [%-s]: \t%.2f\t%.2f\n", e2,
        sum{j1 in L[1]}u2[j1,j2]*MS2[e2],
        l2[e2,j2];
    }
}
printf "=======================================\n";
printf "THC-Team CNES\tFlow\tLack/Excess\n";
printf "=======================================\n";
for{j3 in EL[3]: sum{j2 in L[2]}u3[j2,j3] > 0}{
    printf"L[%-2d]\n", j3;
    for{e3 in E[3]}{
        printf"  [%-s]: %.2f\t%.2f\t%.2f\n", e3, CNES3[e3,j3],
        sum{j2 in L[2]}u3[j2,j3]*MS3[e3],
        l3[e3,j3];
    }
}
for{j3 in CL[3]: sum{j2 in L[2]}u3[j2,j3] > 0}{
    printf"L[%-d*]\n", j3;
    for{e3 in E[3]: sum{j2 in L[2]}u3[j2,j3]>0}{
        printf"  [%-s]: \t%.2f\t%.2f\n", e3,
        sum{j2 in L[2]}u3[j2,j3]*MS3[e3],
        l3[e3,j3];
    }
}

printf "=======================================\n";
printf "PHC  [p]:\tCapty\tMet\tUse(%%)\n";
printf "=======================================\n";
# Existing location
printf{j1 in EL[1], p in P}:
"[%-3d][%d]:\t%d\t%d\t%3d%%\n", j1, p,
C1[p,j1],
sum{i in I}u1[p,i,j1],
((sum{i in I}u1[p,i,j1])/(C1[p,j1]))*100;
# Candidate location
printf{j1 in CL[1], p in P: sum{i in I}u1[p,i,j1]>0}:
"[%-2d*][%d]:\t%d\t%d\t%3d%%\n", j1, p,
C1[p,j1],
sum{i in I}u1[p,i,j1],
((sum{i in I}u1[p,i,j1])/(C1[p,j1]))*100;

printf "=======================================\n";
printf "SHC     :\tCapty\tMet\tUse(%%)\n";
printf "=======================================\n";
# Existing location
printf{j2 in EL[2]}: "[%-6d]:\t%d\t%d\t%3d%%\n", j2,
C2[j2],
sum{j1 in L[1]}u2[j1,j2],
((sum{j1 in L[1]}u2[j1,j2])/(C2[j2]))*100;
# Candidate location
printf{j2 in CL[2]: sum{j1 in L[1]}u2[j1,j2]>0}: "[%-5d*]:\t%d\t%d\t%3d%%\n", j2,
C2[j2],
sum{j1 in L[1]}u2[j1,j2],
((sum{j1 in L[1]}u2[j1,j2])/(C2[j2]))*100;

printf "=======================================\n";
printf "THC     :\tCapty\tMet\tUse(%%)\n";
printf "=======================================\n";
# Existing location
printf{j3 in EL[3]}: "[%-6d]:\t%d\t%d\t%3d%%\n", j3,
C3[j3],
sum{j2 in L[2]}u3[j2,j3],
((sum{j2 in L[2]}u3[j2,j3])/(C3[j3]))*100;
# Candidate location
printf{j3 in CL[3]: sum{j2 in L[2]}u3[j2,j3]>0}: "[%-5d*]:\t%d\t%d\t%3d%%\n", j3,
C3[j3],
sum{j2 in L[2]}u3[j2,j3],
((sum{j2 in L[2]}u3[j2,j3])/(C3[j3]))*100;
printf "=======================================\n\n";

end;
