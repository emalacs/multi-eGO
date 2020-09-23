#!/bin/bash
# for-loopcmd.sh 

# This script makes different pdb in different steps and calculate the rdf
# First, makes a trajectory with the frames at the ts we want
# Second, makes based on the pdbs, it computes the rdf
array=("0" "1" "2" "3" "4" "5" "6" "7" "8" "9" "10" "11")
mkdir rdf 
 

echo -e 0 \n 0 \n | gmx_mpi trjconv -f prod_2000-1mM.xtc -s prod_2000-1mM.tpr -dt 50000 -e 500000 -o rdf/step_.pdb -sep
for ((i=0;i<${#array[@]}; ++i)); do
	 echo ${array[i]} ${array[i]} \n | gmx_mpi trjconv -f prod_2000-1mM.xtc -s prod_2000-1mM.tpr -n pdb.ndx -dt 50000 -e 500000 -center -pbc mol -o rdf/traj_${array[i]} 

	 for ((z=0; z<11; z++)); do
	 	 printf "${array[i]} \n ${array[i]} \n" | gmx_mpi rdf -f rdf/step_$z.pdb -o rdf/clust_${array[i]}_$z -s prod_2000-1mM.tpr -surf mol -rmax 10 -bin 0.05 -nice 1 -n pdb.ndx
	 done 

	 paste rdf/clust_${array[i]}_*.xvg | grep -v "[@:#]" | awk ' {printf $1" "; for(i=2; i<=NF; i=i+2) printf $i" "; print""} '  > rdf/full_clust_${array[i]}.xvg 

done 

rm rdf/#*
exit
