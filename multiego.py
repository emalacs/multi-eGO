import os
import pandas as pd
import sys, getopt
from read_input import read_pdbs, plainMD_mdmat, random_coil_mdmat, read_topology_atoms, read_topology_bonds
from write_output import write_LJ, write_atomtypes_atp, write_topology_atoms, write_pairs_exclusion
from greta import make_pairs_exclusion_topology, PDB_LJ_pairs, MD_LJ_pairs, merge_and_clean_LJ, make_pdb_atomtypes, make_more_atomtypes 
pd.options.mode.chained_assignment = None  # default='warn'

def main(argv):

    parameters = {
        #
        'distance_cutoff':5.5,
        #
        'distance_residue':2,
        #
        'ratio_threshold':0.001,
        # Settings for LJ 1-4. We introduce some LJ interactions otherwise lost with the removal of explicit H
        # The c12 of a LJ 1-4 is too big, therefore we reduce by a factor
        'lj_reduction':0.15,
        # For left alpha we might want to increase the c6 values
        'multiply_c6':1.5,
        # Acid FFnonbondend it only works on the native pairs
        'acid_ff':False,
        #
        'ensemble':True
        # The following parameters are added later from input arguments
        # protein:
        # egos:
        # epsilon_input:
        # epsilon_structure:
        # epsilon_md:
        # input_folder:
        # output_folder:
    }

    print('\n\nMulti-eGO (codename: GRETA)\n')

    readall=0

    try:
        opts, args = getopt.getopt(argv,"",["protein=","egos=","epsilon=","noensemble","help"])
    except getopt.GetoptError:
        print('multiego.py --protein <protein> --egos <single|merge|rc> --epsilon=0.x (not used with --egos=rc) --noensemble (optional)')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '--help':
            print('multiego.py --protein <protein> --egos <single|merge|rc> --epsilon=0.x (not used with --egos=rc) --noensemble (optional)')
            sys.exit()
        elif opt in ("--protein"):
            if not arg:
                print('Provide a protein name')
                sys.exit()
            else:
                parameters['protein'] = arg
                readall +=1
        elif opt in ("--egos"):
            if arg in ('single', 'merge', 'rc'):
                parameters['egos'] = arg
                if arg == 'rc':
                    readall +=2
                else:
                    readall +=1
            else:
                print('--egos accepts <single|merge|rc> options')
                sys.exit()

        elif opt in ("--epsilon"):
            arg = float(arg)
            if arg > 1 or arg < 0:
                print('Epsilon values must be chosen between 0 and 1')
                sys.exit()
            else:
                parameters['epsilon_input'] = float(arg)
                parameters['epsilon_structure'] = float(arg)
                parameters['epsilon_md'] = float(arg)
                readall +=1
        elif opt in ("--noensemble"):
            parameters['ensemble'] = False 
  
    if readall != 3:
        print('ERROR: missing input argument')
        print('multiego.py --protein <protein> --egos <single|merge|rc> --epsilon=0.x (not used with --egos=rc) --noensemble (optional)' )
        exit()

    parameters['input_folder'] = f"inputs/{parameters['protein']}" 
 
    # Folders to save the output files generated by the script
    if parameters['egos'] == 'rc':
        parameters['output_folder'] = f"outputs/{parameters['protein']}_{parameters['egos']}"
    else:
        parameters['output_folder'] = f"outputs/{parameters['protein']}_{parameters['egos']}_e{parameters['epsilon_input']}"

    print('- Creating a multi-eGO force-field using the following parameters:')
    for k,v in parameters.items():
        print('\t{:<20}: {:<20}'.format(k,v))
    
    try:
        os.mkdir(parameters['output_folder'])
    except OSError as error:
        pass

    print('- reading TOPOLOGY')
    print('\tReading ', f'{parameters["input_folder"]}/topol.top')
    topology_atoms = read_topology_atoms(parameters).df_topology_atoms
    topology_bonds = read_topology_bonds(parameters)

    print('- reading PDB')
    native_pdb = read_pdbs(parameters, False)
    if parameters['egos'] == 'merge':
        fibril_pdb = read_pdbs(parameters, True)

    print('- Generating Atomtypes')
    native_atomtypes, ffnonbonded_atp, atomtypes_atp, type_c12_dict = make_pdb_atomtypes(native_pdb, topology_atoms, parameters)
    if parameters['egos'] == 'merge':
        fibril_atomtypes = make_more_atomtypes(fibril_pdb)

    write_atomtypes_atp(atomtypes_atp, parameters)
    write_topology_atoms(topology_atoms, parameters)

    print('- Generating LJ Interactions')

    if parameters['egos'] == 'rc':
        greta_ffnb = pd.DataFrame(columns=['; ai', 'aj', 'type', 'c6', 'c12', '', 'sigma', 'epsilon'])
        write_LJ(ffnonbonded_atp, greta_ffnb, parameters)
        print('- Generating Pairs and Exclusions')
        topology_pairs, topology_exclusion = make_pairs_exclusion_topology(type_c12_dict, topology_atoms, topology_bonds, parameters)
        write_pairs_exclusion(topology_pairs, topology_exclusion, parameters)

    elif parameters['egos'] == 'single':
        if parameters['ensemble'] == True:
            atomic_mat_plainMD = plainMD_mdmat(parameters)
            atomic_mat_random_coil = random_coil_mdmat(parameters)
            greta_LJ = MD_LJ_pairs(atomic_mat_plainMD, atomic_mat_random_coil, parameters)
        else:
            atomic_mat_random_coil = random_coil_mdmat(parameters)
            greta_LJ = PDB_LJ_pairs(native_pdb, atomic_mat_random_coil, native_atomtypes, parameters)
            acid_atp = read_topology_atoms(parameters).acid_atp
            if parameters['acid_ff'] == True and acid_atp !=0:
                    greta_LJ = greta_LJ[~greta_LJ.ai.isin(acid_atp)]
                    greta_LJ = greta_LJ[~greta_LJ.aj.isin(acid_atp)]

    elif parameters['egos'] == 'merge':
        if parameters['ensemble'] == True:
            atomic_mat_plainMD = plainMD_mdmat(parameters)
            atomic_mat_random_coil = random_coil_mdmat(parameters)
            greta_LJ = MD_LJ_pairs(atomic_mat_plainMD, atomic_mat_random_coil, parameters)
            greta_LJ = pd.concat([greta_LJ,PDB_LJ_pairs(fibril_pdb, atomic_mat_random_coil, fibril_atomtypes, parameters)], axis=0, sort = False, ignore_index = True)
        else:
            atomic_mat_random_coil = random_coil_mdmat(parameters)
            greta_LJ = PDB_LJ_pairs(native_pdb, atomic_mat_random_coil, native_atomtypes, parameters)
            acid_atp = read_topology_atoms(parameters).acid_atp
            if parameters['acid_ff'] == True and acid_atp !=0:
                    greta_LJ = greta_LJ[~greta_LJ.ai.isin(acid_atp)]
                    greta_LJ = greta_LJ[~greta_LJ.aj.isin(acid_atp)]
            greta_LJ = pd.concat([greta_LJ,PDB_LJ_pairs(fibril_pdb, atomic_mat_random_coil, fibril_atomtypes, parameters)], axis=0, sort = False, ignore_index = True)

    else: # one should never get here
        print("I dont' understand --egos=",parameters['egos'])
        exit()

    if parameters['egos'] != 'rc':
        print('- Finalising LJ interactions')
        greta_ffnb = merge_and_clean_LJ(greta_LJ, parameters)
        write_LJ(ffnonbonded_atp, greta_ffnb, parameters)

        print('- Generating Pairs and Exclusions')
        topology_pairs, topology_exclusion = make_pairs_exclusion_topology(type_c12_dict, topology_atoms, topology_bonds, parameters, greta_ffnb)
        write_pairs_exclusion(topology_pairs, topology_exclusion, parameters)

    print('- Force-Field files saved in ' + parameters['output_folder'])
    print('\nGRETA completed! Carlo is happy\n')


if __name__ == "__main__":
   main(sys.argv[1:])
