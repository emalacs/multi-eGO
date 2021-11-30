import pandas as pd
from protein_configuration import protein, distance_residue, distance_cutoff
import MDAnalysis as mda
from gromologist import Top

def read_pdbs():
    
    native_directory = 'inputs/native_%s/native.pdb' %(protein)
    fibril_directory = 'inputs/fibril_%s/conf.pdb' %(protein)
    #fibril_directory = 'fibril_%s/proto_double.pdb' %(protein)
    native_pdb = mda.Universe(native_directory, guess_bonds = True)
    fibril_pdb = mda.Universe(fibril_directory, guess_bonds = True)

    return native_pdb, fibril_pdb

def read_top():
    native_directory = 'inputs/native_%s/topol.top' %(protein)
    #native_directory = 'gromologist/examples/01_pentapeptide/topol.top'
    native_pdb = 'inputs/native_%s/native.pdb' %(protein)
    native_topology = Top(native_directory, gmx_dir='/home/emanuele/MAGROS', pdb=native_pdb)
    
    return native_topology

def read_native_pairs():
    #native_directory = 'native_%s/monomer_pairs_amber_ex%s.txt' %(protein, distance_residue)
    native_directory = 'inputs/native_%s/monomer_pairs_md_ex%s_co%s.txt' %(protein, distance_residue, distance_cutoff)
    native_pairs = pd.read_csv(native_directory, sep = '\\s+', header = None)
    native_pairs.columns = ['ai', 'aj', 'counts', 'ratio', 'distance']

    return native_pairs