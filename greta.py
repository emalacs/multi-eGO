from operator import concat
import MDAnalysis as mda
from MDAnalysis.lib.util import parse_residue
from MDAnalysis.analysis import distances
import numpy as np
from pandas.core.frame import DataFrame
import pandas as pd
import itertools
import parmed as pmd
from read_input import random_coil_mdmat, plainMD_mdmat
import mdtraj as md
from topology_parser import read_topology, topology_parser, extra_topology_ligands

pd.options.mode.chained_assignment = None  # default='warn'
pd.options.mode.chained_assignment = 'warn' 


gromos_atp = pd.DataFrame(
    {'name': ['O', 'OA', 'N', 'C', 'CH1', 
            'CH2', 'CH3', 'CH2r', 'NT', 'S',
            'NR', 'OM', 'NE', 'NL', 'NZ'],
     'at.num': [8, 8, 7, 6, 6, 6, 6, 6, 7, 16, 7, 8, 7, 7, 7],
     'c12': [1e-06, 1.505529e-06, 2.319529e-06, 4.937284e-06, 9.70225e-05, # CH1
            3.3965584e-05, 2.6646244e-05, 2.8058209e-05, 5.0625e-06, 1.3075456e-05,
            3.389281e-06, 7.4149321e-07, 2.319529e-06, 2.319529e-06, 2.319529e-06],
     # here the 0 should be corrected with the correct c6 (anyway they are not used now)
     'c6': [0.0022619536, 0, 0, 0, 0.00606841, 0.0074684164, 0.0096138025, 0, 0, 0, 0, 0, 0, 0, 0]
     }
)
gromos_atp.to_dict()
gromos_atp.set_index('name', inplace=True)

class multiego_ensemble:
    '''
    This ensemble type gathers different topologies to make a single one.
    '''
    # Checklist of topology sections we need
    multiego_ensemble_top = pd.DataFrame()

    moleculetype = ''
    bonds = pd.DataFrame()
    bond_pairs = pd.DataFrame()
    angles = pd.DataFrame()
    dihedrals = pd.DataFrame()
    impropers = pd.DataFrame()
        
    ligand_bonds = pd.DataFrame()
    ligand_bond_pairs = []
    ligand_angles = pd.DataFrame()
    ligand_dihedrals = pd.DataFrame()

    pairs = pd.DataFrame()
    exclusions = pd.DataFrame()

    structure_based_contacts_dict = {
        'random_coil' : pd.DataFrame(),
        'atomic_mat_plainMD' : pd.DataFrame(),
        'native_pairs' : pd.DataFrame(),
        'fibril_pairs' : pd.DataFrame(),
        'ligand_MD_pairs' : pd.DataFrame()
    }

    greta_LJ = pd.DataFrame(columns=['; ai', 'aj', 'type', 'c6', 'c12', 'sigma', 'epsilon'])
    
    def __init__(self, parameters):
        self.parameters = parameters


    def multiego_wrapper():
        '''
        Check based on the attribute. Provides all the ensemble, check the attributes of each and then makes the merge 
        '''
        pass

    def add_ensemble_top(self, ensemble_toadd):
        '''
        This method allow the addition of atoms into the multi-eGO ensemble
        '''
        # ATOMTYPES
        ensemble_top = ensemble_toadd.ensemble_top.copy()
        ensemble_top['idx_sbtype'] = ensemble_top['sb_type']
        ensemble_top.set_index(['idx_sbtype'], inplace = True)
        ensemble_top.drop(columns=['index'], inplace=True)

        multiego_idx = self.multiego_ensemble_top.index
        ensemble_idx = ensemble_top.index
        diff_index = ensemble_idx.difference(multiego_idx)
        if not diff_index.empty:
            #print(f'\t- The following atoms are being inserted in multiego topology: {list(diff_index)}')
            print(f'\t- Inserting atoms in multiego ensemble')
        ensemble_top = ensemble_top.loc[diff_index]
        ensemble_top.sort_values(by=['atom_number'], inplace=True)
        self.multiego_ensemble_top = pd.concat([self.multiego_ensemble_top, ensemble_top], axis=0, sort=False)
    
        # Those will be recreated after the addition of all atoms, including the ligand ones
        type_c12_dict = self.multiego_ensemble_top[['sb_type', 'c12']].copy()
        type_c12_dict.rename(columns={'sb_type':'; type'}, inplace=True)
        type_c12_dict = type_c12_dict.set_index('; type')['c12'].to_dict()
        self.type_c12_dict = type_c12_dict

        return self
    
    
    def add_parsed_topology(self, ensemble_toadd):
        self.moleculetype = ensemble_toadd.parsed_topology.moleculetype.copy()
        self.bonds = ensemble_toadd.bonds.copy()
        self.bond_pairs = ensemble_toadd.bond_pairs.copy()
        self.angles = ensemble_toadd.angles.copy()
        self.dihedrals = ensemble_toadd.dihedrals.copy()
        self.impropers = ensemble_toadd.impropers.copy()
        self.system = ensemble_toadd.parsed_topology.system.copy()
        self.molecules = ensemble_toadd.parsed_topology.molecules.copy()
        
        return self

        
    def add_structure_based_contacts(self, **contacts):
        '''
        Names to use: random_coil, atomic_mat_plainMD, native_pairs, fibril_pairs, ligand_MD_pairs
        '''
        for name, value in contacts.items():
            self.structure_based_contacts_dict[name] = value
        self.structure_based_contacts_dict = self.structure_based_contacts_dict
        return self

        
    def generate_multiego_LJ(self):
        
        # TODO ACID DEMMERDA
        #if parameters['acid_ff'] == True and top.acid_atp !=0:
        #        greta_LJ = greta_LJ[~greta_LJ.ai.isin(top.acid_atp)]
        #        greta_LJ = greta_LJ[~greta_LJ.aj.isin(top.acid_atp)]

        #print(self.structure_based_contacts_dict)
        greta_MD_LJ = pd.DataFrame()
        greta_native_SB_LJ = pd.DataFrame()
        greta_fibril_SB_LJ = pd.DataFrame()
        ligand_MD_LJ = pd.DataFrame()
        
        if not self.structure_based_contacts_dict['random_coil'].empty:
            if not self.structure_based_contacts_dict['atomic_mat_plainMD'].empty:
                greta_MD_LJ = MD_LJ_pairs(self.structure_based_contacts_dict['atomic_mat_plainMD'], self.structure_based_contacts_dict['random_coil'], self.parameters)
            if not self.structure_based_contacts_dict['native_pairs'].empty:
                # TODO to compute here the sb types and not in the fibril ensemble
                greta_native_SB_LJ = self.structure_based_contacts_dict['native_pairs']
            
            if not self.structure_based_contacts_dict['fibril_pairs'].empty:
                # TODO to compute here the sb types and not in the fibril ensemble
                greta_fibril_SB_LJ = self.structure_based_contacts_dict['fibril_pairs']
            
            if not self.structure_based_contacts_dict['ligand_MD_pairs'].empty:
                ligand_MD_LJ = self.structure_based_contacts_dict['ligand_MD_pairs']

        greta_LJ = pd.concat([greta_MD_LJ, greta_native_SB_LJ, greta_fibril_SB_LJ, ligand_MD_LJ], axis=0, sort=False, ignore_index=True)

        if greta_LJ.empty:
            greta_ffnb = greta_LJ 
            greta_lj14 = greta_LJ
        else:
            greta_ffnb, greta_lj14 = merge_and_clean_LJ(greta_LJ, self.parameters)
       
        self.greta_ffnb = greta_ffnb
        self.greta_lj14 = greta_lj14

        return self
        
    def generate_pairs_exclusions(self):
        # Here different bonds_pairs should be added:
        # from native and MD they should be the same, the ligand will be added.
        # Then here the pairs and exclusions will be made.

        bond_pairs = self.bond_pairs# + self.ligand_bond_pairs
        topology_pairs, topology_exclusions = make_pairs_exclusion_topology(self.multiego_ensemble_top, bond_pairs, self.type_c12_dict, self.parameters, 
                                                                            self.greta_lj14) 
        self.pairs = topology_pairs
        self.exclusions = topology_exclusions

        return self

    def add_parsed_ligand_topology(self, ensemble_toadd):
        '''
        This one will be kept separated by the protein parsed topology since the definitions are different
        '''
        self.ligand_moleculetype = ensemble_toadd.ligand_moleculetype.copy()
        self.ligand_topology = ensemble_toadd.ensemble_top.copy()
        self.ligand_bonds = ensemble_toadd.ligand_bonds.copy()
        self.ligand_bond_pairs = ensemble_toadd.ligand_pair_bonds.copy()
        self.ligand_angles = ensemble_toadd.ligand_angles.copy()
        self.ligand_dihedrals = ensemble_toadd.ligand_dihedrals.copy()
        
        # This is used when when want to read ligand pairs from the original topology
        # We might want to remove this part
        self.ligand_pairs = ensemble_toadd.ligand_pairs

        return self

    def list_acid_pH(self):
        # ACID pH
        # Selection of the aminoacids and the charged atoms (used for B2m)
        # TODO add some options for precise pH setting
        acid_ASP = self.ensemble_top[(ensemble_top['residue'] == "ASP") & ((self.ensemble_top['atom'] == "OD1") | (self.ensemble_top['atom'] == "OD2") | (self.ensemble_top['atom'] == "CG"))]
        acid_GLU = self.ensemble_top[(ensemble_top['residue'] == "GLU") & ((self.ensemble_top['atom'] == "OE1") | (self.ensemble_top['atom'] == "OE2") | (self.ensemble_top['atom'] == "CD"))]
        acid_HIS = self.ensemble_top[(ensemble_top['residue'] == "HIS") & ((self.ensemble_top['atom'] == "ND1") | (self.ensemble_top['atom'] == "CE1") | (self.ensemble_top['atom'] == "NE2") | (self.ensemble_top['atom'] == "CD2") | (self.ensemble_top['atom'] == "CG"))]
        frames = [acid_ASP, acid_GLU, acid_HIS]
        acid_atp = pd.concat(frames, ignore_index = True)
        #this is used
        self.acid_atp = acid_atp['sb_type'].tolist()
        return self


    def generate_outputs_toWrite(self):
        # Single and merge are right
        # Topol.top is left
        #pd.set_option('display.colheader_justify', 'left')
        pd.set_option('display.colheader_justify', 'right')

        self.moleculetype_toWrite = self.moleculetype.to_string(index=False)

        ffnonbonded_atp = self.multiego_ensemble_top[['sb_type', 'atomic_number', 'mass', 'charge', 'ptype', 'c6', 'c12']].copy()
        ffnb_colnames = ['; type', 'at.num', 'mass', 'charge', 'ptype', 'c6', 'c12']
        ffnonbonded_atp.columns = ffnb_colnames
        ffnonbonded_atp['c12'] = ffnonbonded_atp['c12'].map(lambda x:'{:.6e}'.format(x))
        self.ffnonbonded_atp_toWrite = ffnonbonded_atp.to_string(index = False)
        
        atomtypes_top = self.multiego_ensemble_top[['atom_number', 'sb_type', 'residue_number', 'residue', 'atom', 'cgnr']].copy()
        atomtypes_top.rename(columns = {'atom_number':'; nr', 'sb_type':'type', 'residue_number':'resnr'}, inplace=True)
        self.atomtypes_top_toWrite = atomtypes_top.to_string(index=False)
        
        atomtypes_atp = self.multiego_ensemble_top[['sb_type', 'mass']].copy()
        atomtypes_atp.rename(columns={'sb_type':'; type'}, inplace=True)
        self.atomtypes_atp_toWrite = atomtypes_atp.to_string(index = False, header = False)

        bonds = self.bonds
        bonds.rename(columns = {'ai':'; ai'}, inplace=True)
        self.bonds_toWrite = bonds.to_string(index=False)
        angles = self.angles
        angles.rename(columns = {'ai':'; ai'}, inplace=True)
        self.angles_toWrite = angles.to_string(index=False)
        dihedrals = self.dihedrals
        dihedrals.rename(columns = {'ai':'; ai'}, inplace=True)
        self.dihedrals_toWrite = dihedrals.to_string(index=False)
        impropers = self.impropers
        impropers.rename(columns = {'ai':'; ai'}, inplace=True)
        self.impropers_toWrite = impropers.to_string(index=False)
        pairs = self.pairs
        pairs.rename(columns = {'ai':'; ai'}, inplace=True)
        self.pairs_toWrite = pairs.to_string(index=False)
        exclusions = self.exclusions
        exclusions.rename(columns = {'ai':'; ai'}, inplace=True)
        self.exclusions_toWrite = exclusions.to_string(index=False)
        #self.system_toWrite = self.system.to_string(index=False)
        self.system_toWrite = self.parameters['protein']
        self.molecules_toWrite = self.molecules.to_string(index=False)

        if not self.parameters['egos'] == 'rc': 
            self.greta_ffnb.insert(5, '', ';')
            self.greta_ffnb = self.greta_ffnb.rename(columns = {'ai':'; ai'})
            self.greta_ffnb['epsilon'] = self.greta_ffnb["epsilon"].map(lambda x:'{:.6f}'.format(x))
            self.greta_ffnb['sigma'] = self.greta_ffnb["sigma"].map(lambda x:'{:.6e}'.format(x))
            self.greta_ffnb['c6'] = self.greta_ffnb["c6"].map(lambda x:'{:.6e}'.format(x))
            self.greta_ffnb['c12'] = self.greta_ffnb["c12"].map(lambda x:'{:.6e}'.format(x))
            self.greta_ffnb = self.greta_ffnb[['; ai', 'aj', 'type', 'c6', 'c12', '', 'sigma', 'epsilon', 'same_chain', 'rc_probability']]
            self.greta_ffnb_toWrite = self.greta_ffnb.to_string(index = False)

        if self.parameters['ligand'] == True:
            self.ligand_moleculetype_toWrite = self.ligand_moleculetype.to_string(index=False)
            
            ligand_ffnonbonded_atp = self.ligand_topology[['sb_type', 'atomic_number', 'mass', 'charge', 'ptype', 'c6', 'c12']].copy()
            ffnb_colnames = ['; type', 'at.num', 'mass', 'charge', 'ptype', 'c6', 'c12']
            ligand_ffnonbonded_atp.columns = ffnb_colnames
            ligand_ffnonbonded_atp['c12'] = ligand_ffnonbonded_atp['c12'].map(lambda x:'{:.6e}'.format(x))
            ffnonbonded_atp = pd.concat([ffnonbonded_atp, ligand_ffnonbonded_atp], axis=0, sort=False, ignore_index=True)
            self.ffnonbonded_atp_toWrite = ffnonbonded_atp.to_string(index = False)

            ligand_atomtypes_top = self.ligand_topology[['atom_number', 'sb_type', 'residue_number', 'residue', 'atom', 'cgnr']].copy()
            #ligand_atomtypes_top['atom_number'] = list(range(1, len(ligand_atomtypes_top['atom_number'])+1))
            ligand_atomtypes_top['residue'] = 1
            ligand_atomtypes_top['cgnr'] = 1
            ligand_atomtypes_top.rename(columns = {'atom_number':'; nr', 'sb_type':'type', 'residue_number':'resnr'}, inplace=True)
            self.ligand_atomtypes_top_toWrite = ligand_atomtypes_top.to_string(index=False)
            ligand_bonds = self.ligand_bonds
            ligand_bonds.rename(columns = {'ai':'; ai'}, inplace=True)
            self.ligand_bonds_toWrite = ligand_bonds.to_string(index=False)
            ligand_angles = self.ligand_angles
            ligand_angles.rename(columns = {'ai':'; ai'}, inplace=True)
            self.ligand_angles_toWrite = ligand_angles.to_string(index=False)
            ligand_dihedrals = self.ligand_dihedrals
            ligand_dihedrals.rename(columns = {'ai':'; ai'}, inplace=True)
            self.ligand_dihedrals_toWrite = ligand_dihedrals.to_string(index=False)
            ligand_pairs = self.ligand_pairs
            ligand_pairs.rename(columns = {'ai':'; ai'}, inplace=True)
            ligand_pairs['c6'] = ligand_pairs['c6'].map(lambda x:'{:.6e}'.format(x))
            ligand_pairs['c12'] = ligand_pairs['c12'].map(lambda x:'{:.6e}'.format(x))
            self.ligand_pairs_toWrite = ligand_pairs.to_string(index=False)
            ligand_exclusions = self.ligand_pairs[['; ai', 'aj']].copy()
            self.ligand_exclusions_toWrite = ligand_exclusions.to_string(index=False)

        return self


class ensemble:
    '''
    Ensemble class: aggregates all the parameters used in the script.
    '''
    def __init__(self, parameters, ensemble_parameters):        
        # Topology Section
        # Atoms
        print('\t- Generating ensemble Atomtypes')
        print('\t- Reading topology and structure')
        self.parameters = parameters
        self.ensemble_parameters = ensemble_parameters
        self.topology = pmd.load_file(ensemble_parameters['topology_file'], parametrize=False)
        self.structure = pmd.load_file(ensemble_parameters['structure_file'])


    def prepare_ensemble(self, add_native_ensemble = False):
        ensemble_top = prepare_ensemble_topology(self.topology, self.structure, self.ensemble_parameters, self.parameters)
        self.ensemble_top = ensemble_top
        print('\t- Ensemble topology generated')
        
        sbtype_idx_dict = ensemble_top[['atom_number', 'sb_type']].copy()
        sbtype_idx_dict = sbtype_idx_dict.set_index('sb_type')['atom_number'].to_dict()
        self.sbtype_idx_dict = sbtype_idx_dict

        native_atomtypes = (ensemble_top['sb_type'] +':'+ ensemble_top['chain']).tolist()
        self.native_atomtypes = native_atomtypes
        
        type_c12_dict = ensemble_top[['sb_type', 'c12']].copy()
        type_c12_dict.rename(columns={'sb_type':'; type'}, inplace=True)
        type_c12_dict = type_c12_dict.set_index('; type')['c12'].to_dict()
        self.type_c12_dict = type_c12_dict

        idx_sbtype_dict = ensemble_top[['atom_number', 'sb_type']].copy()
        idx_sbtype_dict = idx_sbtype_dict.set_index('atom_number')['sb_type'].to_dict()
        self.idx_sbtype_dict = idx_sbtype_dict

        return self


    def get_parsed_topology(self):
        '''
        Topol.top sort of things except atoms. Namely bonds, angles, dihedrals, impropers, pairs and exclusions.
        This method uses the parser i wrote and not ParmEd.
        '''
        parsed_topology = topology_parser(read_topology(self.ensemble_parameters['topology_file']))

        # This one is self so i wrote less things in multiego and here
        self.parsed_topology = parsed_topology
        
        self.bonds = parsed_topology.bonds
        bond_pairs = parsed_topology.bond_pairs
        self.bond_pairs = bond_pairs
        self.angles = parsed_topology.angles
        self.dihedrals = parsed_topology.dihedrals
        self.impropers = parsed_topology.impropers

        return self


    def match_native_topology(self, sbtype_idx_dict):
        '''
        Fibril might not be entirely modelled, therefore the numbering does not match the native structure.
        Here a dictionary is supplied to renumber the atoms.
        '''

        print('\t- Renumbering the fibril atom numbers')
        self.ensemble_top['atom_number'] = self.ensemble_top['sb_type'].map(sbtype_idx_dict)
        return self
    
    def convert_topology(self, ego_native):
        '''
        This functions is needed to convert the structure based atomtypes from a force field to gromos.
        It is tested using charmm were the only different atomtypes are OT1 and OT2 which has to be renamed to O1 and O2.
        Other differences are on the atom index which is solved using the structure based atomtype.
        Here a dictionary is made by charmm key: gromos value.
        '''
        multiego_topology = ego_native.ensemble_top
        md_topology = self.ensemble_top

        multiego_atoms = set(multiego_topology['atom'].to_list())
        md_atoms = set(md_topology['atom'].to_list())
        diff_atoms = list(multiego_atoms - md_atoms)
        
        merged_atoms = pd.DataFrame()
        merged_atoms['atoms_multiego'] = multiego_topology['atom']
        merged_atoms['multiego_resnum'] = multiego_topology['residue_number']
        merged_atoms['atoms_md'] = md_topology['atom']
        merged_atoms['md_resnum'] = md_topology['residue_number']
        merged_atoms = merged_atoms.loc[merged_atoms['atoms_multiego'].isin(diff_atoms)]
        merged_atoms['sb_multiego'] = merged_atoms['atoms_multiego']+'_'+merged_atoms['multiego_resnum'].astype(str)
        merged_atoms['sb_md'] = merged_atoms['atoms_md']+'_'+merged_atoms['md_resnum'].astype(str)
        merged_atoms_dict = merged_atoms.set_index('sb_md')['sb_multiego'].to_dict()

        md_topology = md_topology.replace({'sb_type':merged_atoms_dict})
        self.ensemble_top = md_topology
        updated_mat_plainMD = self.atomic_mat_MD
        updated_mat_plainMD = updated_mat_plainMD.replace({'ai':merged_atoms_dict})
        updated_mat_plainMD = updated_mat_plainMD.replace({'aj':merged_atoms_dict})
        self.atomic_mat_MD = updated_mat_plainMD
        self.conversion_dict = merged_atoms_dict

        return self


    def add_random_coil(self):
        # The random coil should come from the same native ensemble
        #if not ensemble_parameters['not_matching_native']:
        atomic_mat_random_coil = random_coil_mdmat(self.parameters, self.idx_sbtype_dict)
        self.atomic_mat_random_coil = atomic_mat_random_coil
        return self
        
        
    def add_MD_contacts(self):
        # MD_contacts
        atomic_mat_MD = plainMD_mdmat(self.parameters, self.ensemble_parameters, self.idx_sbtype_dict)
        self.atomic_mat_MD = atomic_mat_MD
        return self
    

    def get_structure_pairs(self, ego_native):
        print('\t- Reading pdb structure for pairs')
        mda_structure = mda.Universe(self.ensemble_parameters['structure_file'], guess_bonds = False)#, topology_format='PDB')
        print('\t- Making pairs')
        structure_pairs = PDB_LJ_pairs(mda_structure, ego_native.atomic_mat_random_coil, self.native_atomtypes, self.parameters)
        self.structure_pairs = structure_pairs
        return self


    def get_ligand_ensemble(self): # TODO change name
        '''
        Reading ligand .itp and .prm to get topology parameters to add in topol_ligand and ffnonbonded.itp.
        Parameters are ligand C6 and C12, bonds, angles, dihedrals and pairs.
        '''
        # ATOMS
        # Here is just filtering by the ligand 
        ligand_residue_number = self.ensemble_top['residue_number'].max()
        self.ligand_residue_number = ligand_residue_number

        # extra atomtypes for c12 definitions
        print('\t - Retrieving ligand extra atom definitions')
        itp = read_topology(self.ensemble_parameters['itp_file'])
        prm = read_topology(self.ensemble_parameters['prm_file'])
        extra_ligand_top = extra_topology_ligands(itp, prm, ligand_residue_number)

        self.ligand_moleculetype = extra_ligand_top.ligand_moleculetype

        # Inserting the new c12 in ffnonbonded.itp
        ligand_ensemble_top = self.ensemble_top.loc[self.ensemble_top['residue_number'] == ligand_residue_number]
        ligand_ensemble_top['c12'] = ligand_ensemble_top['sb_type'].map(extra_ligand_top.ligand_sbtype_c12_dict)
        ligand_ensemble_top['atom_number'] = ligand_ensemble_top['sb_type'].map(extra_ligand_top.sbtype_ligand_number_dict)
        #ligand_ensemble_top['c12'] = ligand_ensemble_top['c12'].map(lambda x:'{:.6e}'.format(x))
        self.ensemble_top = ligand_ensemble_top
        
        ligand_sbtype_number_dict = ligand_ensemble_top[['sb_type', 'atom_number']].copy()
        ligand_sbtype_number_dict = ligand_sbtype_number_dict.set_index('sb_type')['atom_number'].to_dict()   
        self.ligand_sbtype_number_dict = ligand_sbtype_number_dict

        update_ligand_bonds = extra_ligand_top.ligand_bonds
        update_ligand_bonds['ai'] = update_ligand_bonds['ai'].map(ligand_sbtype_number_dict)
        update_ligand_bonds['aj'] = update_ligand_bonds['aj'].map(ligand_sbtype_number_dict)
        update_ligand_bonds.dropna(inplace=True)
        update_ligand_bonds['ai'] = update_ligand_bonds['ai'].astype(int)
        update_ligand_bonds['aj'] = update_ligand_bonds['aj'].astype(int)
        # This is for gromacs which is bitchy
        update_ligand_bonds['c1'] = update_ligand_bonds['c1']/self.parameters['ligand_reduction']
        self.ligand_bonds = update_ligand_bonds
        bond_pairs = list([(str(ai), str(aj)) for ai, aj in zip(update_ligand_bonds['ai'].to_list(), update_ligand_bonds['aj'].to_list())])
        self.ligand_pair_bonds = bond_pairs

        update_ligand_angles = extra_ligand_top.ligand_angles
        update_ligand_angles['ai'] = update_ligand_angles['ai'].map(ligand_sbtype_number_dict)
        update_ligand_angles['aj'] = update_ligand_angles['aj'].map(ligand_sbtype_number_dict)
        update_ligand_angles['ak'] = update_ligand_angles['ak'].map(ligand_sbtype_number_dict)
        update_ligand_angles.dropna(inplace=True)
        update_ligand_angles['ai'] = update_ligand_angles['ai'].astype(int)
        update_ligand_angles['aj'] = update_ligand_angles['aj'].astype(int)
        update_ligand_angles['ak'] = update_ligand_angles['ak'].astype(int)
        self.ligand_angles = update_ligand_angles

        update_ligand_dihedrals = extra_ligand_top.ligand_dihedrals
        update_ligand_dihedrals['ai'] = update_ligand_dihedrals['ai'].map(ligand_sbtype_number_dict)
        update_ligand_dihedrals['aj'] = update_ligand_dihedrals['aj'].map(ligand_sbtype_number_dict)
        update_ligand_dihedrals['ak'] = update_ligand_dihedrals['ak'].map(ligand_sbtype_number_dict)
        update_ligand_dihedrals['al'] = update_ligand_dihedrals['al'].map(ligand_sbtype_number_dict)
        update_ligand_dihedrals.dropna(inplace=True)
        update_ligand_dihedrals['ai'] = update_ligand_dihedrals['ai'].astype(int)
        update_ligand_dihedrals['aj'] = update_ligand_dihedrals['aj'].astype(int)
        update_ligand_dihedrals['ak'] = update_ligand_dihedrals['ak'].astype(int)
        update_ligand_dihedrals['al'] = update_ligand_dihedrals['al'].astype(int)
        self.ligand_dihedrals = update_ligand_dihedrals

        # This is used when when want to read ligand pairs from the original topology
        # We might want to remove this part
        update_ligand_pairs = extra_ligand_top.ligand_pairs
        update_ligand_pairs['ai'] = update_ligand_pairs['ai'].map(ligand_sbtype_number_dict)
        update_ligand_pairs['aj'] = update_ligand_pairs['aj'].map(ligand_sbtype_number_dict)
        update_ligand_pairs.dropna(inplace=True)
        update_ligand_pairs['ai'] = update_ligand_pairs['ai'].astype(int)
        update_ligand_pairs['aj'] = update_ligand_pairs['aj'].astype(int)
        self.ligand_pairs = update_ligand_pairs
        
        return self
     

    def ligand_MD_LJ_pairs(self):
        # TODO this one will be moved in multiego_ensemble
        print('\t- Adding the ligand LJ potential')

        # Following the idea that the ligand is considered as a residue in the same chain,
        # we select ligand pairs by selecting the spare residue compared with the ligand
        atomic_ligand_mat = self.atomic_mat_MD
        # Drop values below md_treshold, otherwise the epsilon will be negative
        atomic_ligand_mat.drop(atomic_ligand_mat[atomic_ligand_mat['probability'] < self.parameters['md_threshold']].index, inplace=True)
        #atomic_ligand_mat.drop(atomic_ligand_mat[atomic_ligand_mat['probability'] <= 0].index, inplace=True)
        # Filtering for the ligand
        #atomic_ligand_mat.dropna(inplace=True)
        atomic_ligand_mat = atomic_ligand_mat.loc[(atomic_ligand_mat['residue_ai'] == self.ligand_residue_number) | (atomic_ligand_mat['residue_aj'] == self.ligand_residue_number)]
        self_interactions = atomic_ligand_mat.loc[(atomic_ligand_mat['residue_ai'] == self.ligand_residue_number) & (atomic_ligand_mat['residue_aj'] == self.ligand_residue_number)]
        
        # TODO to be fixed. Here I am removing the self contacts of the ligand which with the latest updates causes the molecules to overlap.
        # Namely, with the new update more self ligand contacts are retained with a very high probability.
        # A quick and dirty fix is to remove such self contacts, but those should be added in pairs and exclusions properly.
        mask = ((atomic_ligand_mat['residue_ai'] == self.ligand_residue_number) & (atomic_ligand_mat['residue_aj'] == self.ligand_residue_number))
        #print(atomic_ligand_mat[mask].to_string())
        atomic_ligand_mat = atomic_ligand_mat[~mask]

        atomic_ligand_mat['sigma'] = (atomic_ligand_mat['distance']) / (2**(1/6))
        atomic_ligand_mat[['idx_ai', 'idx_aj']] = atomic_ligand_mat[['ai', 'aj']]
        atomic_ligand_mat.set_index(['idx_ai', 'idx_aj'], inplace = True)
        
        # We are using the old equation (prior to the RC version)
        atomic_ligand_mat['epsilon'] = self.parameters['epsilon_ligand']*(1-((np.log(atomic_ligand_mat['probability']))/(np.log(self.parameters['md_threshold']))))
        atomic_ligand_mat.drop(columns = ['distance', 'residue_ai', 'residue_aj', 'probability'], inplace = True)
        atomic_ligand_mat.dropna(inplace=True)
        atomic_ligand_mat = atomic_ligand_mat[atomic_ligand_mat.epsilon != 0]
        self.ligand_atomic_mat_MD = atomic_ligand_mat

        return self



# END CLASS



# TODO this one might be included in the ensemble class
def prepare_ensemble_topology(topology, structure, ensemble_parameters, parameters):
    print('\t\t- Checking the atoms in both Topology and Structure')
    for atom_top, atom_struct in zip(topology.atoms, structure.atoms):
        if str(atom_top) != str(atom_struct):
            print('- Topology and structure have different atom definitions\n\n')
            print(atom_top, atom_struct)
            exit()
    print('\t\t- Atoms between Topology and Structure are corresponding')
    
    topology_df = topology.to_dataframe()
    structure_df = structure.to_dataframe()

    print('\t\t- Generating multi-eGO topology')
    multiego_top = pd.DataFrame()
    multiego_top['atom_number'] = structure_df['number']
    multiego_top['atom_type'] = topology_df['type']
    multiego_top['residue_number'] = structure_df['resnum']
    multiego_top['residue'] = structure_df['resname']
    multiego_top['atom'] = topology_df['name']
    multiego_top['cgnr'] = structure_df['resnum']
    multiego_top['mass'] = topology_df['mass']
    multiego_top['atomic_number'] = topology_df['atomic_number']
    #multiego_top['chain'] = chain_ids
    multiego_top['chain'] = structure_df['chain']
    multiego_top['charge'] = '0.000000'
    multiego_top['ptype'] = 'A'
    multiego_top['c6'] = '0.00000e+00'
    multiego_top['c12'] = multiego_top['atom_type'].map(gromos_atp['c12'])

    #if ensemble_parameters['is_MD'] == True:
    print('\t\t- Removing Hydrogens')
    # MD has hydrogen which we don't use
    hydrogen = topology['@H=']
    hydrogen_number = len(hydrogen.atoms)
    hydrogen_namelist = []
    for h in hydrogen.atoms:
        hydrogen_namelist.append(h.name)
    hydrogen_namelist = list(set(hydrogen_namelist))
    # Multi-eGO topology
    mask = (multiego_top['atom']).isin(hydrogen_namelist)
    multiego_top = multiego_top[~mask]
    multiego_top.reset_index(inplace=True)
    multiego_top['atom_number'] = multiego_top.index+1

    print('\t\t- Topology fixes')
    # Removing an extra H to PRO
    pd.options.mode.chained_assignment = None 

    mask = ((multiego_top['residue'] == "PRO") & (multiego_top['atom_type'] == 'N'))
    multiego_top['mass'][mask] = multiego_top['mass'][mask].astype(float).sub(1)
    # Adding an extra H to the N terminal
    mask = ((multiego_top['residue_number'] == multiego_top['residue_number'].min()) & (multiego_top['atom_type'] == 'N'))
    multiego_top['mass'][mask] = multiego_top['mass'][mask].astype(float).add(2)

    # Aromatic carbons dictionary
    aromatic_carbons_dict = {
        'PHE': ['CD1', 'CD2', 'CE1', 'CE2', 'CZ'],
        'TYR': ['CD1', 'CD2', 'CE1', 'CE2'],
        'HIS': ['CE1', 'CD2'],
        'TRP': ['CD1', 'CE3', 'CZ2', 'CZ3', 'CH2']
    }

    for resname, atomnames in aromatic_carbons_dict.items():
        for atom in atomnames:
            mask = ((multiego_top['residue'] == resname) & (multiego_top['atom'] == atom))
            multiego_top['mass'][mask] = multiego_top['mass'][mask].astype(float).add(1)

    print('\t\t- Defining multi-eGO atomtypes')
    multiego_top['sb_type'] = multiego_top['atom'] + '_' + multiego_top['residue_number'].astype(str)

    return multiego_top


def make_file_dictionary_todelete(filename):
    file_dict = {}
    with open(filename) as f:
        for line_number, line in enumerate(f):
            if line.startswith('ATOM'):
                file_dict[line_number+1] = line.strip()
    return file_dict


def rename_chains_todelete(structure_dict, chain_ids, file_name):
    # Change the column number 22 which is the chain id in the pdb
    column = 22 - 1
    file_name = file_name.split('/')
    file_path = file_name[:-1]
    file_name = file_name[-1]
    file_name = file_name.split('.')
    file_name = '/'.join(file_path)+'/'+file_name[0]+'_renamed.'+file_name[1]
    with open(file_name, 'w') as scrivi:
        for (line, string), chain_id in zip(structure_dict.items(), chain_ids):
            new_string = string[0:column]+str(chain_id)+string[column+1:]
            scrivi.write(f"{new_string}\n")
    
    return file_name


def get_topology_bonds_todelete(topology):
    bond_atom1, bond_atom2, bond_funct = [], [], []
    for bond in topology.bonds:
        bond_atom1.append(bond.atom1.idx+1)
        bond_atom2.append(bond.atom2.idx+1)
        bond_funct.append(bond.funct)
        # TODO Here is missing the gd_definition, maybe in writing the input will solve this
        #print(dir(bond))
        #print(bond.type)

    bonds_df = pd.DataFrame()
    bonds_df['ai'] = bond_atom1
    bonds_df['aj'] = bond_atom2
    bonds_df['funct'] = bond_funct

    return bonds_df

# TODO this one might be included in the ensemble class
def sb_type_conversion(multiego_ensemble, md_ensemble):
    '''
    This functions is needed to convert the structure based atomtypes from a force field to gromos.
    It is tested using charmm were the only different atomtypes are OT1 and OT2 which has to be renamed to O1 and O2.
    Other differences are on the atom index which is solved using the structure based atomtype.
    Here a dictionary is made by charmm key: gromos value.
    '''

    multiego_topology = multiego_ensemble.multiego_topology
    md_topology = md_ensemble.multiego_topology

    convert_dict = {}
    multiego_atoms = set(multiego_topology['atom'].to_list())
    md_atoms = set(md_topology['atom'].to_list())
    diff_atoms = list(multiego_atoms - md_atoms)
    merged_atoms = pd.DataFrame()
    merged_atoms['atoms_multiego'] = multiego_topology['atom']
    merged_atoms['multiego_resnum'] = multiego_topology['residue_number']
    merged_atoms['atoms_md'] = md_topology['atom']
    merged_atoms['md_resnum'] = md_topology['residue_number']
    merged_atoms = merged_atoms.loc[merged_atoms['atoms_multiego'].isin(diff_atoms)]
    merged_atoms['sb_multiego'] = merged_atoms['atoms_multiego']+'_'+merged_atoms['multiego_resnum'].astype(str)
    merged_atoms['sb_md'] = merged_atoms['atoms_md']+'_'+merged_atoms['md_resnum'].astype(str)
    merged_atoms_dict = merged_atoms.set_index('sb_md')['sb_multiego'].to_dict()
    
    updated_mat_plainMD = md_ensemble.atomic_mat_plainMD
    updated_mat_plainMD = updated_mat_plainMD.replace({'ai':merged_atoms_dict})
    updated_mat_plainMD = updated_mat_plainMD.replace({'aj':merged_atoms_dict})

    return updated_mat_plainMD, merged_atoms_dict


def ligand_MD_LJ_pairs_todelete(ego_ligand, parameters):
    # TODO this one will be moved in multiego_ensemble
    print('\t- Adding the ligand LJ potential')

    # Following the idea that the ligand is considered as a residue in the same chain,
    # we select ligand pairs by selecting the spare residue compared with the ligand
    atomic_ligand_mat = ego_ligand.atomic_mat_MD
    atomic_ligand_mat = atomic_ligand_mat.loc[(atomic_ligand_mat['residue_ai'] == ego_ligand.ligand_residue_number) | (atomic_ligand_mat['residue_aj'] == ego_ligand.ligand_residue_number)]
    atomic_ligand_mat['sigma'] = (atomic_ligand_mat['distance']) / (2**(1/6))
    atomic_ligand_mat[['idx_ai', 'idx_aj']] = atomic_ligand_mat[['ai', 'aj']]
    atomic_ligand_mat.set_index(['idx_ai', 'idx_aj'], inplace = True)
    
    # We are using the old equation (prior to the RC version)
    atomic_ligand_mat['epsilon'] = parameters['epsilon_input']*(1-((np.log(atomic_ligand_mat['probability']))/(np.log(parameters['ratio_threshold']))))
    atomic_ligand_mat.drop(columns = ['distance', 'residue_ai', 'residue_aj', 'probability'], inplace = True)
    atomic_ligand_mat.dropna(inplace=True)
    atomic_ligand_mat = atomic_ligand_mat[atomic_ligand_mat.epsilon != 0]

    return atomic_ligand_mat


# TODO todelete
def make_pdb_atomtypes(native_pdb, topology_atoms, parameters):
    '''
    This function prepares the ffnonbonded.itp section of Multi-ego.ff.
    The topology of the plainMD is read, and custom c12 are added.
    The native .pdb is read and a list of the atoms is prepared to use in PDB_LJ_pairs.
    It also provides a dictionary based on atom_type and c12 used in make_pairs_exclusion_topology.
    '''
    native_sel = native_pdb.select_atoms('all')
    native_atomtypes, ffnb_sb_type = [], []

    for atom in native_sel:
        '''
        This loop is required for the atom list to be used in PDB_LJ_pairs.
        '''
        # Native atomtypes will be used to create the pairs list
        #TODO print another for check
        atp = str(atom.name) + '_' + str(atom.resnum) + ':' + str(atom.segid)
        native_atomtypes.append(atp)

        # This part is for attaching to FFnonbonded.itp
        # ffnb_sb_type is the first column
        # check gromologist
        sb_type = str(atom.name) + '_' + str(atom.resnum)
        ffnb_sb_type.append(sb_type)

    check_topology = DataFrame(ffnb_sb_type, columns=['sb_type'])
    check_topology = check_topology.drop_duplicates(subset=['sb_type'])
    check_topology['check'] = np.where(topology_atoms.sb_type == check_topology.sb_type, 'same', 'different')
    
    # Just checking that the pdb and the topology have the same number of atoms
    if len(np.unique(check_topology.check)) != 1:
        print('\n\tCheck PDB and topology because they have different numbers of atoms')
        exit()
        
    # ffnonbonded making
    # Making a dictionary with atom number and type
    ffnb_atomtype = pd.DataFrame(columns = ['; type', 'chem', 'at.num', 'mass', 'charge', 'ptype', 'c6', 'c12'])
    ffnb_atomtype['; type'] = topology_atoms['sb_type']
    ffnb_atomtype['chem'] = topology_atoms['atom_type']
    ffnb_atomtype['at.num'] = ffnb_atomtype['chem'].map(gromos_atp['at.num'])
    ffnb_atomtype['mass'] = topology_atoms['mass']
    ffnb_atomtype['charge'] = '0.000000'
    ffnb_atomtype['ptype'] = 'A'
    ffnb_atomtype['c6'] = '0.00000e+00'
    ffnb_atomtype['c12'] = ffnb_atomtype['chem'].map(gromos_atp['c12'])
    
    
    # This will be needed for exclusion and pairs to paste in topology
    # A dictionary with the c12 of each atom in the system
    type_c12_dict = ffnb_atomtype.set_index('; type')['c12'].to_dict()
    
    ffnb_atomtype['c12'] = ffnb_atomtype["c12"].map(lambda x:'{:.6e}'.format(x))
    ffnb_atomtype.drop(columns = ['chem'], inplace = True)

    atomtypes_atp = ffnb_atomtype[['; type', 'mass']].copy()

    return native_atomtypes, ffnb_atomtype, atomtypes_atp, type_c12_dict

# TODO todelete
def make_more_atomtypes(fibril_pdb):
    '''
    Like the previous one, this part is needed in PDB_LJ_pairs when computing the pairs.
    '''
    fibril_sel = fibril_pdb.select_atoms('all')
    fibril_atomtypes = []
    for atom in fibril_sel:
        atp = str(atom.name) + '_' + str(atom.resnum) + ':' + str(atom.segid)
        fibril_atomtypes.append(atp)

    return fibril_atomtypes

# TODO todelete
def topology_check(top1, top2):
    if top1 == top2:
        print('- Same topology definitions')
    else:
        difference = set(top1).symmetric_difference(set(top2))
        atom_difference = list(difference)
        #print(atom_difference)


def PDB_LJ_pairs(structure_pdb, atomic_mat_random_coil, atomtypes, parameters):
    '''
    This function measures all the distances between all atoms using MDAnalysis.
    It works on both native and fibril in the same manner.
    Pairs are filtered based on the distance_cutoff which is fixed at 5.5A (in main parameters).
    A second filter is based on the distance_residue. Pairs between atoms closer than two residues are removed 
    if the contact is in the same chain.
    The function also provides the sigma and the epsilon of each pair.
    In case of intramolecular contacts, pairs are reweighted based on the random_coil probability
    '''
    print('\tAddition of PDB derived native LJ-pairs')

    print('\t\tMeasuring distances between all atom in the structure')
    # Selecting all atoms in the system
    atom_sel = structure_pdb.select_atoms('all')

    # Calculating all the distances between atoms.
    # The output is a combination array.
    self_distances = distances.self_distance_array(atom_sel.positions)
    print('\t\tNumber of distances measured :', len(self_distances))
    
    # The MDAnalysis contains only distances, so we rebuilt atom pairs in the same manner
    # using the atomtypes list of native and fibril which will match with the distance array.

    # TODO create directly the two separated lists
    pairs_list = list(itertools.combinations(atomtypes, 2))

    # But the combinations are list of list and we need to separate them.
    pairs_ai, pairs_aj = [], []
    for n in range(0, len(pairs_list)):
        i = pairs_list[n][0]
        pairs_ai.append(i)
        j = pairs_list[n][1]
        pairs_aj.append(j)

    # Creation of the dataframe containing the atom pairs and the distances.
    # Also, it will be prepared for sigma and epsilon.
    structural_LJ = pd.DataFrame(columns = ['ai', 'aj', 'distance', 'sigma', 'epsilon'])
    structural_LJ['ai'] = pairs_ai
    structural_LJ['aj'] = pairs_aj
    structural_LJ['distance'] = self_distances
    print('\t\tRaw pairs list ', len(structural_LJ))
    
    # Keep only the atoms within cutoff
    structural_LJ = structural_LJ[structural_LJ.distance < parameters["distance_cutoff"]] # PROTEIN CONFIGURATION
    print(f'\t\tPairs below cutoff {parameters["distance_cutoff"]}: ', len(structural_LJ))

    # That is name_resname:resid made from the previous function.
    # Extracting the resid information to check if the atom pair is on the same chain.
    structural_LJ[['ai', 'chain_ai']] = structural_LJ.ai.str.split(":", expand = True)
    structural_LJ[['aj', 'chain_aj']] = structural_LJ.aj.str.split(":", expand = True)
    structural_LJ['same_chain'] = np.where(structural_LJ['chain_ai'] == structural_LJ['chain_aj'], 'Yes', 'No')
    
    print('\t\tPairs within the same chain: ', len(structural_LJ.loc[structural_LJ['same_chain'] == 'Yes']))
    print('\t\tPairs not in the same chain: ', len(structural_LJ.loc[structural_LJ['same_chain'] == 'No']))

    # if two pairs are made by aminoacids closer than X they'll be deleted. 
    structural_LJ[['type_ai', 'resnum_ai']] = structural_LJ.ai.str.split("_", expand = True)
    structural_LJ[['type_aj', 'resnum_aj']] = structural_LJ.aj.str.split("_", expand = True)
    # And to do that it is necessary to convert the two columns into integer
    structural_LJ = structural_LJ.astype({"resnum_ai": int, "resnum_aj": int})
    structural_LJ['diffr'] = abs(structural_LJ['resnum_aj'] - structural_LJ['resnum_ai'])
    structural_LJ.drop(structural_LJ[(structural_LJ['diffr'] < parameters['distance_residue']) & (structural_LJ['same_chain'] == 'Yes')].index, inplace = True)    
    
    # Inverse pairs calvario
    # this must list ALL COLUMNS!
    inv_LJ = structural_LJ[['aj', 'ai', 'distance', 'sigma', 'epsilon', 'chain_ai', 'chain_aj', 'same_chain', 'type_ai', 'resnum_ai', 'type_aj', 'resnum_aj', 'diffr']].copy()
    inv_LJ.columns = ['ai', 'aj', 'distance', 'sigma', 'epsilon', 'chain_ai', 'chain_aj', 'same_chain', 'type_ai', 'resnum_ai', 'type_aj', 'resnum_aj', 'diffr']
    structural_LJ = pd.concat([structural_LJ, inv_LJ], axis=0, sort = False, ignore_index = True)
    # Here we sort all the atom pairs based on the distance and we keep the closer ones, but prioritising intermolecular contacts.
    # Sorting the pairs
    structural_LJ.sort_values(by = ['ai', 'aj', 'same_chain', 'distance'], ascending = [True, True, True, True], inplace = True)

    inter_LJ = structural_LJ.loc[structural_LJ['same_chain'] == 'No']
    # this is to correctly account for the double counting
    inter_LJ[['ai', 'aj']] = np.sort(inter_LJ[['ai', 'aj']].values, axis=1)
    # here we keep track of the duplicates only on intermolecular contacts
    num = inter_LJ.groupby(by=['ai','aj']).size().reset_index().rename(columns={0:'records'})
    # add the count of duplicates
    structural_LJ = pd.merge(structural_LJ, num, how="right", on=["ai", "aj"])
    print(structural_LJ.to_string())

    # Cleaning the duplicates
    structural_LJ = structural_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    # Removing the reverse duplicates
    cols = ['ai', 'aj']
    structural_LJ[cols] = np.sort(structural_LJ[cols].values, axis=1)
    structural_LJ = structural_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    structural_LJ[['idx_ai', 'idx_aj']] = structural_LJ[['ai', 'aj']]
    structural_LJ.set_index(['idx_ai', 'idx_aj'], inplace=True)
    print(f'\t\tAll the pairs after removing duplicates: ', len(structural_LJ))

    inter_mask = structural_LJ['same_chain'] == 'No'
    intra_mask = structural_LJ['same_chain'] == 'Yes'
    diff_mask =  structural_LJ['diffr'] < parameters['distance_residue']

    # normalise the duplicates (only for intermolecular contacts)
    structural_LJ['records'] /=  float(structural_LJ[inter_mask]['records'].mode())
    structural_LJ['sigma'] = (structural_LJ['distance']/10) / (2**(1/6))
    #structural_LJ['epsilon'].loc[(inter_mask)] = structural_LJ['records'].pow(0.5)*parameters['epsilon_md']
    structural_LJ['epsilon'].loc[(inter_mask)&(structural_LJ['records']>=1.)] = parameters['epsilon_amyl']
    structural_LJ['epsilon'].loc[(inter_mask)&(structural_LJ['records']<1.)] = parameters['epsilon_md']
    structural_LJ['epsilon'].loc[(inter_mask)&(structural_LJ['records']<0.2)] = 0. 
    #structural_LJ['epsilon'].loc[(intra_mask)] = parameters['epsilon_md']
    print(structural_LJ['records'].min())

    # Take the contact from different chains 
    #is_bb =  (((structural_LJ['type_ai']=="N")|(structural_LJ['type_ai']=="CA")|(structural_LJ['type_ai']=="C")|(structural_LJ['type_ai']=="O"))&
    #          ((structural_LJ['type_aj']=="N")|(structural_LJ['type_aj']=="CA")|(structural_LJ['type_aj']=="C")|(structural_LJ['type_aj']=="O")))
    
    #is_bb_cb = ((((structural_LJ['type_ai']=="N")|(structural_LJ['type_ai']=="CA")|(structural_LJ['type_ai']=="C")|(structural_LJ['type_ai']=="O"))&(structural_LJ['type_aj']=="CB"))|
    #            ((structural_LJ['type_ai']=="CB")&((structural_LJ['type_aj']=="N")|(structural_LJ['type_aj']=="CA")|(structural_LJ['type_aj']=="C")|(structural_LJ['type_aj']=="O"))))

    #structural_LJ['epsilon'].loc[(inter_mask)&(diff_mask)&(is_bb)] = parameters['epsilon_amyl']
    #structural_LJ['epsilon'].loc[(inter_mask)&(diff_mask)&(is_bb_cb)] = parameters['epsilon_amyl']

    atomic_mat_random_coil[['idx_ai', 'idx_aj']] = atomic_mat_random_coil[['rc_ai', 'rc_aj']]
    atomic_mat_random_coil.set_index(['idx_ai', 'idx_aj'], inplace = True)
    # Using inner ho un dataframe vuoto, dunque vuol dire che i contatti tra nativa e fibrilla sono completamente diversi
    # E' un caso generico da prevedere
    structural_LJ = pd.concat([structural_LJ, atomic_mat_random_coil], axis=1, join='inner')
    structural_LJ['epsilon'].loc[(intra_mask)&(structural_LJ['rc_probability']<0.999)] = -(parameters['epsilon_md']/np.log(parameters['rc_threshold']))*(np.log(0.999/structural_LJ['rc_probability']))
    structural_LJ['epsilon'].loc[(intra_mask)&(structural_LJ['rc_probability']>=0.999)] = 0 
    structural_LJ['epsilon'].loc[(structural_LJ['epsilon'] < 0.01*parameters['epsilon_md'])] = 0
    structural_LJ.dropna(inplace=True)
    structural_LJ = structural_LJ[structural_LJ.epsilon != 0]

    print('\t\tSigma and epsilon completed ', len(structural_LJ))
    structural_LJ.drop(columns = ['distance', 'chain_ai', 'chain_aj', 'type_ai', 'resnum_ai', 'type_aj', 'resnum_aj', 'rc_ai',  'rc_aj',  'rc_distance', 'rc_residue_ai', 'rc_residue_aj', 'diffr', 'records'], inplace = True)

    return structural_LJ


def MD_LJ_pairs(atomic_mat_plainMD, atomic_mat_random_coil, parameters):
    '''
    This function reads the probabilities obtained using mdmat on the plainMD and the random coil simulations.
    For each atom contact the sigma and epsilon are obtained.
    '''
    print('\tAddition of MD derived LJ-pairs')

    # Add sigma, add epsilon reweighted, add c6 and c12
    atomic_mat_plainMD['sigma'] = (atomic_mat_plainMD['distance']) / (2**(1/6))
    # Merge the two dataframes by ai and aj which are also indexes now
    atomic_mat_plainMD[['idx_ai', 'idx_aj']] = atomic_mat_plainMD[['ai', 'aj']]
    atomic_mat_plainMD.set_index(['idx_ai', 'idx_aj'], inplace = True)

    atomic_mat_random_coil[['idx_ai', 'idx_aj']] = atomic_mat_random_coil[['rc_ai', 'rc_aj']]
    atomic_mat_random_coil.set_index(['idx_ai', 'idx_aj'], inplace = True)

    atomic_mat_merged = pd.concat([atomic_mat_plainMD, atomic_mat_random_coil], axis=1)

    # Epsilon reweight based on probability
    atomic_mat_merged['epsilon'] = ''    

    # Paissoni Equation 2.0
    # Attractive pairs
    #atomic_mat_merged['epsilon'].loc[(atomic_mat_merged['probability'] >=  atomic_mat_merged['rc_probability'])] = epsilon_md*(1-((np.log(atomic_mat_merged['probability']))/(np.log(atomic_mat_merged['rc_probability']))))
    # Repulsive pairs test
    #atomic_mat_merged['epsilon'].loc[(atomic_mat_merged['probability'] <  atomic_mat_merged['rc_probability'])] = -(epsilon_md*(1-((np.log(atomic_mat_merged['rc_probability']))/(np.log(atomic_mat_merged['probability'])))))
    #atomic_mat_merged['sigma'].loc[(atomic_mat_merged['probability'] <  atomic_mat_merged['rc_probability'])] = atomic_mat_merged['rc_distance']/(2**(1/6))

    # Paissoni Equation 2.1
    # Attractive
    atomic_mat_merged['epsilon'].loc[(atomic_mat_merged['probability'] >= atomic_mat_merged['rc_probability'])] = -(parameters['epsilon_md']/np.log(parameters['rc_threshold']))*(np.log(atomic_mat_merged['probability']/atomic_mat_merged['rc_probability']))
    # Repulsive
    atomic_mat_merged['epsilon'].loc[(atomic_mat_merged['probability'] < atomic_mat_merged['rc_probability'])] = (parameters['epsilon_md']/np.log(parameters['md_threshold']))*(np.log(atomic_mat_merged['rc_probability']/atomic_mat_merged['probability']))
    atomic_mat_merged['sigma'].loc[(atomic_mat_merged['probability'] < atomic_mat_merged['rc_probability'])] = atomic_mat_merged['rc_distance']/(2**(1/6))

    # Treshold vari ed eventuali
    atomic_mat_merged['epsilon'].loc[(atomic_mat_merged['probability'] < parameters['md_threshold'])] = 0
    atomic_mat_merged['epsilon'].loc[abs(atomic_mat_merged['epsilon']) < 0.01*parameters['epsilon_md']] = 0
    atomic_mat_merged.drop(columns = ['distance', 'rc_residue_ai', 'rc_residue_aj', 'residue_ai', 'residue_aj', 'probability', 'rc_ai', 'rc_aj', 'rc_distance'], inplace = True)
    atomic_mat_merged.dropna(inplace=True)
    atomic_mat_merged = atomic_mat_merged[atomic_mat_merged.epsilon != 0]

    print("\t\t",len(atomic_mat_merged), " pairs interactions")
    # Inverse pairs calvario
    # this must list ALL COLUMNS!
    inv_LJ = atomic_mat_merged[['aj', 'ai', 'sigma', 'epsilon']].copy()
    inv_LJ.columns = ['ai', 'aj', 'sigma', 'epsilon']
    atomic_mat_merged = pd.concat([atomic_mat_merged, inv_LJ], axis=0, sort = False, ignore_index = True)
    # Here we sort all the atom pairs based on the distance and we keep the closer ones.
    # Sorting the pairs
    atomic_mat_merged.sort_values(by = ['ai', 'aj', 'sigma'], inplace = True)
    # Cleaning the duplicates
    atomic_mat_merged = atomic_mat_merged.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    # Removing the reverse duplicates
    cols = ['ai', 'aj']
    atomic_mat_merged[cols] = np.sort(atomic_mat_merged[cols].values, axis=1)
    atomic_mat_merged = atomic_mat_merged.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    atomic_mat_merged[['idx_ai', 'idx_aj']] = atomic_mat_merged[['ai', 'aj']]
    atomic_mat_merged.set_index(['idx_ai', 'idx_aj'], inplace=True)
    atomic_mat_merged['same_chain'] = 'Yes'
    print(f'\t\t pairs added after removing duplicates: ', len(atomic_mat_merged))
    print("\t\t average epsilon is ", atomic_mat_merged['epsilon'].mean())
    print("\t\t maximum epsilon is ", atomic_mat_merged['epsilon'].max())

    return atomic_mat_merged


def merge_and_clean_LJ(greta_LJ, parameters):
    '''
    This function merges the atom contacts from native and fibril and removed eventual duplicates.
    Also, in case of missing residues in the structure, predicts the self contacts based on the contacts available.
    '''

    print('- Generate Inter and Intra moleculars interactions')
    print('\tMerged pairs list: ', len(greta_LJ))
    print('\tSorting and dropping all the duplicates')
    # Inverse pairs calvario
    inv_LJ = greta_LJ[['aj', 'ai', 'sigma', 'rc_probability', 'epsilon', 'same_chain']].copy()
    inv_LJ.columns = ['ai', 'aj', 'sigma', 'rc_probability', 'epsilon', 'same_chain']
    greta_LJ = pd.concat([greta_LJ,inv_LJ], axis=0, sort = False, ignore_index = True)

    # case 1 #
    # Sorting the pairs shortest distance with positive epsilon
    # greta_LJ.sort_values(by = ['ai', 'aj', 'sigma'], ascending = [True, True, True], inplace = True)
    # between a pair with positive and negative epsilon we keep the one with positive epsilon
    # greta_LJ=greta_LJ[~((greta_LJ.duplicated(subset = ['ai','aj'], keep=False)) & (greta_LJ['epsilon'] < 0.))]
    # Cleaning the duplicates choosing shorter sigmas
    # greta_LJ = greta_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')

    #case 2
    # Sorting the pairs largest epsilon
    # greta_LJ.sort_values(by = ['ai', 'aj', 'epsilon', 'sigma'], ascending = [True, True, False, True], inplace = True)
    # Cleaning the duplicates choosing shorter sigmas
    # greta_LJ = greta_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')

    #case 3
    # pairs averaging using common mix rule
    # greta_LJ.sort_values(by = ['ai', 'aj', 'sigma'], ascending = [True, True, True], inplace = True)
    # between a pair with positive and negative epsilon we keep the one with positive epsilon
    # greta_LJ=greta_LJ[~((greta_LJ.duplicated(subset = ['ai','aj'], keep=False)) & (greta_LJ['epsilon'] < 0.))]
    #greta_LJ=greta_LJ.groupby(by=['ai','aj']).agg({'sigma':'mean', 'epsilon' : lambda x: (x.prod())**(1/x.count()), 'rc_probability':'mean'}).reset_index()

    #case 4
    pairs_LJ = greta_LJ.copy()
    # Greta prioritise intermolecular interactions
    greta_LJ.sort_values(by = ['ai', 'aj', 'same_chain', 'sigma'], ascending = [True, True, True, True], inplace = True)
    greta_LJ=greta_LJ[~((greta_LJ.duplicated(subset = ['ai','aj'], keep=False)) & (greta_LJ['epsilon'] < 0.))]
    greta_LJ = greta_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    # Removing the reverse duplicates
    cols = ['ai', 'aj']
    greta_LJ[cols] = np.sort(greta_LJ[cols].values, axis=1)
    greta_LJ = greta_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    print('\tCleaning ane Merging Complete, pairs count: ', len(greta_LJ))


    # Pairs prioritise intramolecular interactions
    pairs_LJ.sort_values(by = ['ai', 'aj', 'same_chain', 'sigma'], ascending = [True, True, False, True], inplace = True)
    pairs_LJ=pairs_LJ[~((pairs_LJ.duplicated(subset = ['ai','aj'], keep=False)) & (pairs_LJ['epsilon'] < 0.))]
    pairs_LJ = pairs_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    pairs_LJ[cols] = np.sort(pairs_LJ[cols].values, axis=1)
    pairs_LJ = pairs_LJ.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    # where pairs_LJ is the same of greta_LJ and same_chain is yes that the line can be dropped
    # that is I want to keep lines with same_chain no or lines with same chain yes that have same_chain no in greta_LJ
    test = pd.merge(pairs_LJ, greta_LJ, how="right", on=["ai", "aj"])
    pairs_LJ = test.loc[(test['same_chain_x']=='No')|((test['same_chain_x']=='Yes')&(test['same_chain_y']=='No'))]
    pairs_LJ.drop(columns = ['sigma_y', 'epsilon_y', 'same_chain_y', 'rc_probability_y'], inplace = True)
    pairs_LJ.rename(columns = {'sigma_x': 'sigma', 'rc_probability_x': 'rc_probability', 'epsilon_x': 'epsilon', 'same_chain_x': 'same_chain'}, inplace = True)

    greta_LJ.insert(2, 'type', 1)
    greta_LJ.insert(3, 'c6', '')
    greta_LJ['c6'] = 4 * greta_LJ['epsilon'] * (greta_LJ['sigma'] ** 6)
    greta_LJ.insert(4, 'c12', '')
    greta_LJ['c12'] = abs(4 * greta_LJ['epsilon'] * (greta_LJ['sigma'] ** 12))

    pairs_LJ.insert(2, 'type', 1)
    pairs_LJ.insert(3, 'c6', '')
    pairs_LJ['c6'] = 4 * pairs_LJ['epsilon'] * (pairs_LJ['sigma'] ** 6)
    pairs_LJ.insert(4, 'c12', '')
    pairs_LJ['c12'] = abs(4 * pairs_LJ['epsilon'] * (pairs_LJ['sigma'] ** 12))

    # SELF INTERACTIONS
    # In the case of fibrils which are not fully modelled we add self interactions which is a feature of amyloids
    # So that the balance between native and fibril is less steep.
    print('\tSelf interactions')
    atomtypes = set(greta_LJ['ai'])
    greta_LJ['double'] = ''

    for i in atomtypes:
        # Selection of already known atoms which contacts with themself
        greta_LJ.loc[(greta_LJ['ai'] == i) & (greta_LJ['aj'] == i), 'double'] = 'True'

    # Create a subset of the main dataframe of the self interactions.
    doubles = greta_LJ.loc[(greta_LJ['double'] == 'True')]
    atp_doubles = list(doubles['ai'])
    # The list is used to obtain all the atomtypes which does not make a self interaction
    atp_notdoubles = list(set(set(atomtypes) - set(atp_doubles)))
    atp_notdoubles.sort()

    if len(atp_notdoubles) == 0:
        print('\t\tAll atoms interacts with themself')
        
    else:
        print('\t\tThere are', len(atp_notdoubles), 'self interactions to add')
        # From the list of atomtypes to add, a new dataframe is created to append to the main one
        pairs_toadd = pd.DataFrame(columns = ['ai', 'aj', 'type', 'c6', 'c12', 'sigma', 'epsilon'])
        pairs_toadd['ai'] = atp_notdoubles
        pairs_toadd['aj'] = atp_notdoubles
        pairs_toadd['type'] = '1'

        # Here i want to check every value for all the atom type and if they're similar
        # make an average and paste into the main dataframe
        # I am checking every doubles based on the atomtype (except the information of the residue number) and make an average of the sigma
        # since all the epsilon are equal
        atomtypes_toadd = pairs_toadd['ai'].str.split('_', n = 1, expand = True)
        atomtypes_toadd = atomtypes_toadd[0].drop_duplicates()
        atomtypes_toadd = atomtypes_toadd.to_list()
        atomtypes_toadd = [x + '_' for x in atomtypes_toadd]

        for a in atomtypes_toadd:
            # Selects the atom pairs from the double pairs 
            doubles_a = doubles.loc[(doubles['ai'].str.contains(a)) & (doubles['aj'].str.contains(a))]
            # All the epsilon are the same, therefore the average sigma will be added on the self interaction
            sigma = doubles_a['sigma']
            eps = doubles_a['epsilon']
            
            if len(sigma) == 1:
                # If there is only onw sigma for the averages it will be skipped
                print('\t\tOnly one self interacting pair available for {} ==> {}'.format((str(a)[:-1]), 'Skip'))
            elif len(sigma) == 0:
                # If the missing atom pairs is not represented in the strcture there are not
                # sigmas to average
                print('\t\tThere are not self interactions for {:<12} ==> {}'.format((str(a)[:-1]), 'Skip'))
            else:
                # If there are enough sigmas to make an average then it creates the missing atom pairs
                media_sigma = sigma.mean()
                sd_sigma = sigma.std()
                media_epsilon = eps.mean()
                print('\t\tThere are {:<3} {:<3} with an average Sigma of: {:>17.10f} +/- {} epsilon {}'.format((len(sigma)), (str(a)[:-1]), media_sigma, sd_sigma, media_epsilon))
                
                # Creation of new c6 and c12
                # Epsilon structure because those are self
                new_c6 = 4 * media_epsilon * (media_sigma ** 6)
                new_c12 = 4 *media_epsilon * (media_sigma ** 12)

                # In the pairs to add dataframe all those new information are inserted
                pairs_toadd.loc[(pairs_toadd['ai'].str.contains(a)) & (pairs_toadd['aj'].str.contains(a)), 'c6'] = new_c6
                pairs_toadd.loc[(pairs_toadd['ai'].str.contains(a)) & (pairs_toadd['aj'].str.contains(a)), 'c12'] = new_c12
                pairs_toadd.loc[(pairs_toadd['ai'].str.contains(a)) & (pairs_toadd['aj'].str.contains(a)), 'sigma'] = media_sigma
                pairs_toadd.loc[(pairs_toadd['ai'].str.contains(a)) & (pairs_toadd['aj'].str.contains(a)), 'epsilon'] = media_epsilon 

        pairs_toadd.dropna(inplace = True)
        # Appending the missing atom pairs to the main dataframe
        greta_LJ = pd.concat([greta_LJ,pairs_toadd], axis=0, sort = False, ignore_index = True)
        print('\t\tSelf interactions added to greta_LJ ', len(pairs_toadd))

    # Drop double, we don't need it anymore
    greta_LJ.drop(columns = ['double'], inplace = True)

    print('\tLJ Merging completed: ', len(greta_LJ))
    print("\t\t average epsilon is ", greta_LJ['epsilon'].mean())
    print("\t\t maximum epsilon is ", greta_LJ['epsilon'].max())

    return greta_LJ, pairs_LJ


def make_pairs_exclusion_topology(ego_topology, bond_tuple, type_c12_dict, parameters, greta_merge):
    '''
    This function prepares the [ exclusion ] and [ pairs ] section to paste in topology.top
    Here we define the GROMACS exclusion list and drop from the LJ list made using GRETA so that all the remaining
    contacts will be defined in pairs and exclusions as particular cases.
    Since we are not defining explicit H, the 1-4 list is defined by 2 bonds and not 3 bonds.
    This function also fixes the dihedral issue of the left alpha to be explored.
    '''
    if not greta_merge.empty:
        greta_merge = greta_merge.rename(columns = {'; ai': 'ai'})

    ego_topology['atom_number'] = ego_topology['atom_number'].astype(str)
    atnum_type_top = ego_topology[['atom_number', 'sb_type', 'residue_number', 'atom', 'atom_type', 'residue']].copy()
    atnum_type_top['residue_number'] = atnum_type_top['residue_number'].astype(int)

    # Dictionaries definitions to map values
    atnum_type_dict = atnum_type_top.set_index('sb_type')['atom_number'].to_dict()
    type_atnum_dict = atnum_type_top.set_index('atom_number')['sb_type'].to_dict()

    #TODO this should be in topology_definitions.py
    # Building the exclusion bonded list
    # exclusion_bonds are all the interactions within 3 bonds
    # p14 are specifically the interactions at exactly 3 bonds
    ex, ex14, p14, exclusion_bonds = [], [], [], []
    for atom in ego_topology['atom_number'].to_list():
        for t in bond_tuple:
            if t[0] == atom:
                first = t[1]
                ex.append(t[1])
            elif t[1] == atom:
                first = t[0]
                ex.append(t[0])
            else: continue
            for tt in bond_tuple:
                if (tt[0] == first) & (tt[1] != atom):
                    second = tt[1]
                    ex.append(tt[1])
                elif (tt[1] == first) & (tt[0] != atom):
                    second = tt[0]
                    ex.append(tt[0])
                else: continue
                for ttt in bond_tuple:
                    if (ttt[0] == second) & (ttt[1] != first):
                        ex.append(ttt[1])
                        ex14.append(ttt[1])

                    elif (ttt[1] == second) & (ttt[0] != first):
                        ex.append(ttt[0])
                        ex14.append(ttt[0])
        for e in ex:
            exclusion_bonds.append((str(str(atom) + '_' + str(e))))
            exclusion_bonds.append((str(str(e) + '_' + str(atom))))
        ex = []
        for e in ex14:
            p14.append((str(str(atom) + '_' + str(e))))
            p14.append((str(str(e) + '_' + str(atom))))
        ex14 = []

    if not greta_merge.empty:
        # pairs from greta does not have duplicates because these have been cleaned before
        pairs = greta_merge[['ai', 'aj', 'c6', 'c12', 'rc_probability', 'same_chain', 'epsilon']].copy()
        pairs['c12_ai'] = pairs['ai']
        pairs['c12_aj'] = pairs['aj']
        pairs[['type_ai', 'resnum_ai']] = pairs.ai.str.split("_", expand = True)
        pairs[['type_aj', 'resnum_aj']] = pairs.aj.str.split("_", expand = True)
        pairs['resnum_ai'] = pairs['resnum_ai'].astype(int)
        pairs['resnum_aj'] = pairs['resnum_aj'].astype(int)
        
     	# When generating LJ interactions we kept intermolecular interactions between atoms belonging to residues closer than distance residues
        # Now we neeed to be sure that these are excluded intramolecularly
        # If we keep such LJ they cause severe frustration to the system and artifacts
        # pairs = pairs.loc[((abs(pairs['resnum_aj'] - pairs['resnum_ai']) < parameters['distance_residue'])|(pairs['same_chain'] == 'No'))]
        # We remove the contact with itself
        pairs = pairs[pairs['ai'] != pairs['aj']]
        
        # The exclusion list was made based on the atom number
        pairs['ai'] = pairs['ai'].map(atnum_type_dict)
        pairs['aj'] = pairs['aj'].map(atnum_type_dict)
        pairs['check'] = pairs['ai'] + '_' + pairs['aj']
        
        # Here the drop the contacts which are already defined by GROMACS, including the eventual 1-4 exclusion defined in the LJ_pairs
        pairs['exclude'] = ''
        pairs.loc[(pairs['check'].isin(exclusion_bonds)), 'exclude'] = 'Yes' 
        mask = pairs.exclude == 'Yes'
        pairs = pairs[~mask]
        pairs['c12_ai'] = pairs['c12_ai'].map(type_c12_dict)
        pairs['c12_aj'] = pairs['c12_aj'].map(type_c12_dict)
        pairs['func'] = 1
        # riscaliamo anche con eps_max
        ratio = parameters['epsilon_md']/pairs['epsilon'].loc[(pairs['same_chain']=='No')].max()
        print(ratio)
        ratio = pairs['epsilon'].loc[(pairs['same_chain']=='Yes')].max()/pairs['epsilon'].loc[(pairs['same_chain']=='No')].max()
        print(ratio)
        ratio = pairs['epsilon'].loc[(pairs['same_chain']=='Yes')].max()
        #pairs['c6'].loc[(pairs['same_chain']=='No') & (0.9 >= pairs['rc_probability'])] = -(ratio*pairs['c6']/np.log(parameters['rc_threshold']))*(np.log(0.999/pairs['rc_probability']))  
        #pairs['c12'].loc[(pairs['same_chain']=='No') & (0.9 >= pairs['rc_probability'])] = -(ratio*pairs['c12']/np.log(parameters['rc_threshold']))*(np.log(0.999/pairs['rc_probability']))  
        pairs['c6'].loc[(pairs['same_chain']=='No') & (0.9 >= pairs['rc_probability'])] = -(ratio/pairs['epsilon']*pairs['c6']/np.log(parameters['rc_threshold']))*(np.log(0.999/pairs['rc_probability']))  
        pairs['c12'].loc[(pairs['same_chain']=='No') & (0.9 >= pairs['rc_probability'])] = -(ratio/pairs['epsilon']*pairs['c12']/np.log(parameters['rc_threshold']))*(np.log(0.999/pairs['rc_probability']))  
        pairs['c6'].loc[(pairs['same_chain']=='No') & ((0.9 < pairs['rc_probability'])|(abs(pairs['resnum_aj'] - pairs['resnum_ai']) < parameters['distance_residue']))] = 0.  
        pairs['c12'].loc[(pairs['same_chain']=='No') & ((0.9 < pairs['rc_probability'])|(abs(pairs['resnum_aj'] - pairs['resnum_ai']) < parameters['distance_residue']))] = np.sqrt(pairs['c12_ai'] * pairs['c12_aj'])  
        #pairs['c6'] = 0.00000e+00
        #pairs['c12'] = np.sqrt(pairs['c12_ai'] * pairs['c12_aj'])
        pairs.drop(columns = ['rc_probability','same_chain', 'type_ai', 'resnum_ai', 'type_aj', 'resnum_aj', 'c12_ai', 'c12_aj', 'check', 'exclude', 'epsilon'], inplace = True)   
        pairs = pairs[['ai', 'aj', 'func', 'c6', 'c12']]

    else:
        pairs = pd.DataFrame()
    
    # Drop NaNs. This is an issue when adding the ligand ensemble.
    pairs.dropna(inplace=True)
    # Only 1-4 exclusions are fully reintroduced
    pairs_14 = pd.DataFrame(columns=['ai', 'aj', 'exclusions'])
    pairs_14['exclusions'] = p14
    pairs_14[['ai', 'aj']] = pairs_14.exclusions.str.split("_", expand = True)

    pairs_14['c12_ai'] = pairs_14['ai']
    pairs_14['c12_aj'] = pairs_14['aj']
    pairs_14['c12_ai'] = pairs_14['c12_ai'].map(type_atnum_dict)
    pairs_14['c12_aj'] = pairs_14['c12_aj'].map(type_atnum_dict)

    # Adding an atom column because we want to flag NOT N N interactions, this because the N should have an explicit H we removed
    pairs_14[['ai_type', 'ai_resid']] = pairs_14.c12_ai.str.split("_", expand = True)
    pairs_14[['aj_type', 'aj_resid']] = pairs_14.c12_aj.str.split("_", expand = True)

    # NOT 1-4 N-X interactions will be dropped
    pairs_14.loc[(pairs_14['ai_type'] == 'N') | (pairs_14['aj_type'] == 'N'), 'c12_tozero'] = False
    # Here we take a particular interest of the interaction between two N, because both should have an explicit H
    pairs_14.loc[(pairs_14['ai_type'] == 'N') & (pairs_14['aj_type'] == 'N'), 'c12_tozero'] = True
    # Only the pairs with an N involved are retained
    pairs_14.dropna(inplace=True)#(pairs_14[pairs_14.c12_tozero != False].index, inplace=True)

    # Thus, only N with X LJ 1-4 interactions will be kept
    # All the other 1-4 interactions will NOT interact with each others
    pairs_14['c12_ai'] = pairs_14['c12_ai'].map(type_c12_dict)
    pairs_14['c12_aj'] = pairs_14['c12_aj'].map(type_c12_dict)
    pairs_14['func'] = 1
    pairs_14['c6'] = 0.00000e+00
    # in general 1-4 interactions are excluded, N-X 1-4 interactions are retained but scaled down
    pairs_14['c12'] = (np.sqrt(pairs_14['c12_ai'] * pairs_14['c12_aj']))*parameters['lj_reduction']
    
    # The N-N interactions are less scaled down, double the c12
    pairs_14.loc[(pairs_14['c12_tozero'] == True), 'c12'] *= 1.6

    # Removing the interactions with the proline N becasue this does not have the H
    residue_list = ego_topology['residue'].to_list()
    proline_n = []
    if 'PRO' in residue_list:
        proline_n = ego_topology.loc[(ego_topology['residue'] == 'PRO') & (ego_topology['atom'] == 'N'), 'atom_number'].to_list()

    pairs_14 = pairs_14[~pairs_14['ai'].isin(proline_n)]
    pairs_14 = pairs_14[~pairs_14['aj'].isin(proline_n)]

    # Removing the interactions between the glycine N and the N of the following aminoacid 
    glycine_n = []
    glycine_ri = []
    glycine_next_n = []
    if 'GLY' in residue_list:
        glycine_n = ego_topology.loc[(ego_topology['residue'] == 'GLY') & (ego_topology['atom'] == 'N'), 'atom_number'].to_list()
        glycine_ri = ego_topology.loc[(ego_topology['residue'] == 'GLY') & (ego_topology['atom'] == 'N'), 'residue_number'].to_list()
 
    resid_list = ego_topology['residue_number'].to_list()
    
    for i in glycine_ri: 
        glycine_next_n.append(ego_topology.loc[(ego_topology['residue_number'] == i+1) & (ego_topology['atom'] == 'N'), 'atom_number'].to_list()[0])
 
    pairs_14 = pairs_14[~pairs_14['ai'].isin(glycine_n)|~pairs_14['aj'].isin(glycine_next_n)]
    pairs_14 = pairs_14[~pairs_14['aj'].isin(glycine_n)|~pairs_14['ai'].isin(glycine_next_n)]

    pairs_14.drop(columns = ['exclusions', 'c12_ai', 'c12_aj', 'ai_type', 'ai_resid','aj_type', 'aj_resid', 'c12_tozero'], inplace = True)    

    # Exclusions 1-4
    pairs = pd.concat([pairs,pairs_14], axis=0, sort=False, ignore_index=True)

    # Drop duplicates
    pairs.sort_values(by = ['ai', 'aj', 'c12'], inplace = True)
    # Cleaning the duplicates (in case of doubt keep the smallest c12)
    pairs = pairs.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')

    # Removing the reverse duplicates
    cols = ['ai', 'aj']
    pairs[cols] = np.sort(pairs[cols].values, axis=1)
    pairs = pairs.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')

    # Adding the c6 and c12 (I do it now because later is sbatti)
    atnum_type_top['c6'] = atnum_type_top['atom_type'].map(gromos_atp['c6'])
    atnum_type_top['c12'] = atnum_type_top['sb_type'].map(type_c12_dict)

    # Here we make a dictionary of the backbone oxygen as atom number
    backbone_oxygen = atnum_type_top.loc[atnum_type_top['atom'] == 'O']
    backbone_ca_gly = atnum_type_top.loc[(atnum_type_top['atom'] == 'CA')&(atnum_type_top['residue'] == 'GLY')]
    backbone_nitrogen = atnum_type_top.loc[atnum_type_top['atom'] == 'N']
    sidechain_cb = atnum_type_top.loc[atnum_type_top['atom'] == 'CB']
    # CB not used for GLY and PRO and N of PRO
    sidechain_cb = sidechain_cb[sidechain_cb.residue != 'PRO']
    sidechain_cb = sidechain_cb[sidechain_cb.residue != 'GLY']
    backbone_nitrogen = backbone_nitrogen[backbone_nitrogen.residue != 'PRO']

    # Add pair interaction for beta carbon and nitrogen + 1
    nitrogen_interactions_ai, nitrogen_interactions_aj, nitrogen_interactions_c6, nitrogen_interactions_c12 = [], [], [], []
    for index, line_sidechain_cb in sidechain_cb.iterrows():
        line_backbone_n = backbone_nitrogen.loc[(backbone_nitrogen['residue_number']) == (line_sidechain_cb['residue_number']+1)].squeeze(axis=None)
        if not line_backbone_n.empty:
            nitrogen_interactions_ai.append(line_sidechain_cb['atom_number'])
            nitrogen_interactions_aj.append(line_backbone_n['atom_number'])
            nitrogen_interactions_c6.append(0)
            nitrogen_interactions_c12.append(parameters['lj_reduction'] * 7.861728e-06)    # nitrogen c12 times ala cb c12

    nitrogen_interaction_pairs = pd.DataFrame(columns=['ai', 'aj', 'c6', 'c12'])
    nitrogen_interaction_pairs['ai'] = nitrogen_interactions_ai
    nitrogen_interaction_pairs['aj'] = nitrogen_interactions_aj
    nitrogen_interaction_pairs['c6'] = nitrogen_interactions_c6
    nitrogen_interaction_pairs['c12'] = nitrogen_interactions_c12
    nitrogen_interaction_pairs['func'] = 1

    pairs = pd.concat([pairs,nitrogen_interaction_pairs], axis=0, sort=False, ignore_index=True)

    # For each backbone oxygen take the CB of the same residue and save in a pairs tuple
    alpha_beta_rift_ai, alpha_beta_rift_aj, alpha_beta_rift_c6, alpha_beta_rift_c12 = [], [], [], []
    for index, line_backbone_oxygen in backbone_oxygen.iterrows():
        line_sidechain_cb = sidechain_cb.loc[sidechain_cb['residue_number'] == (line_backbone_oxygen['residue_number'])].squeeze(axis=None)
        if not line_sidechain_cb.empty:
            alpha_beta_rift_ai.append(line_backbone_oxygen['atom_number'])
            alpha_beta_rift_aj.append(line_sidechain_cb['atom_number'])
            alpha_beta_rift_c6.append(0.0)
            alpha_beta_rift_c12.append((0.000005162090)*0.2)

    alpha_beta_rift_pairs = pd.DataFrame(columns=['ai', 'aj', 'c6', 'c12'])
    alpha_beta_rift_pairs['ai'] = alpha_beta_rift_ai
    alpha_beta_rift_pairs['aj'] = alpha_beta_rift_aj
    alpha_beta_rift_pairs['c6'] = alpha_beta_rift_c6
    alpha_beta_rift_pairs['c12'] = alpha_beta_rift_c12
    alpha_beta_rift_pairs['func'] = 1

    pairs = pd.concat([pairs,alpha_beta_rift_pairs], axis=0, sort=False, ignore_index=True)

    # add O-1 CA pairs for Glycines
    oca_gly_interactions_ai, oca_gly_interactions_aj, oca_gly_interactions_c6, oca_gly_interactions_c12 = [], [], [], []
    for index, line_backbone_ca_gly in backbone_ca_gly.iterrows():
        line_backbone_o = backbone_oxygen.loc[(backbone_oxygen['residue_number']) == (line_backbone_ca_gly['residue_number']-1)].squeeze(axis=None)
        if not line_backbone_o.empty:
            oca_gly_interactions_ai.append(line_backbone_ca_gly['atom_number'])
            oca_gly_interactions_aj.append(line_backbone_o['atom_number'])
            oca_gly_interactions_c6.append(0)
            oca_gly_interactions_c12.append(6.000000e-06)

    oca_gly_interaction_pairs = pd.DataFrame(columns=['ai', 'aj', 'c6', 'c12'])
    oca_gly_interaction_pairs['ai'] = oca_gly_interactions_ai
    oca_gly_interaction_pairs['aj'] = oca_gly_interactions_aj
    oca_gly_interaction_pairs['c6'] = oca_gly_interactions_c6
    oca_gly_interaction_pairs['c12'] = oca_gly_interactions_c12
    oca_gly_interaction_pairs['func'] = 1

    pairs = pd.concat([pairs,oca_gly_interaction_pairs], axis=0, sort=False, ignore_index=True)

    # Cleaning the duplicates (the left alpha pairs win on pairs that may be previously defined)
    pairs.sort_values(by = ['ai', 'aj', 'c12'], inplace = True)
    pairs = pairs.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    # drop inverse duplicates
    cols = ['ai', 'aj']
    pairs[cols] = np.sort(pairs[cols].values, axis=1)
    pairs = pairs.drop_duplicates(subset = ['ai', 'aj'], keep = 'first')
    pairs['ai'] = pairs['ai'].astype(int)
    pairs['aj'] = pairs['aj'].astype(int)

    # Here we want to sort so that ai is smaller than aj
    inv_pairs = pairs[['aj', 'ai', 'func', 'c6', 'c12']].copy()
    inv_pairs.columns = ['ai', 'aj', 'func', 'c6', 'c12']
    pairs = pd.concat([pairs,inv_pairs], axis=0, sort = False, ignore_index = True)
    pairs = pairs[pairs['ai']<pairs['aj']]
    
    pairs.sort_values(by = ['ai', 'aj'], inplace = True)

    pairs = pairs.rename(columns = {'ai': '; ai'})
    pairs['c6'] = pairs["c6"].map(lambda x:'{:.6e}'.format(x))
    pairs['c12'] = pairs["c12"].map(lambda x:'{:.6e}'.format(x))
    exclusion = pairs[['; ai', 'aj']].copy()

    return pairs, exclusion
