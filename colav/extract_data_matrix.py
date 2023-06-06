
import os, pickle
import numpy as np 
from biopandas.pdb import PandasPdb
from itertools import combinations
from colav.strain_analysis import *
from colav.internal_coordinates import * 
from scipy.spatial.distance import pdist

def calculate_dihedral_transformed_loadings(raw_dihedral_loading): 
    '''
    Calculates a transformed loading from a raw loading of dihedral angle features to account 
    for the application of sine and cosine functions. 

    Returns a transformed loading. 

    Parameters: 
    -----------
    raw_dihedral_loading : array_like, (N,)
    array of raw loading from PCA

    Returns: 
    --------
    transformed_loading : array_like, (N/2,)
    array of transformed loading akin to sin^2 + cos^2 = 1 to determine relative angle influence
    for each principal component
    '''
    
    transformed_loading = np.sqrt(np.power(raw_dihedral_loading[:raw_dihedral_loading.shape[0]//2],2) + \
                          np.power(raw_dihedral_loading[raw_dihedral_loading.shape[0]//2:],2))
    return transformed_loading

def generate_dihedral_matrix(structure_list, resnum_bounds, no_psi=False, no_omega=False, no_phi=False, save=False, verbose=False): 
    '''
    Extracts and returns a data matrix of (observations x features) with the given structures as observations
    and the linearized dihedral angles (by applying sine and cosine functions)  as features. 
    Cannot handle missing coordinates and skips structures with missing backbone atoms within the 
    given residue numbers. 

    Parameters: 
    -----------
    structure_list : array_like 
    array containing the file paths to PDB structures

    resnum_bounds : tuple
    tuple containing the minimum and maximum (inclusive) residue number values

    no_psi : boolean, optional 
    indicator to exclude psi dihedral angle from returned dihedral angles 

    no_omega : boolean, optional 
    indicator to exclude omega dihedral angle from returned dihedral angles

    no_phi : boolean, optional 
    indicator to exclude phi dihedral angle from returne dihedral angles

    save : boolean, optional 
    indicator to save results once determined

    verbose : boolean, optional 
    indicator for verbose output

    Returns: 
    --------
    dh_data_matrix : array_like 
    array containing dihedral angles between desired atoms for all given structures, excluding 
    structures missing desired atoms 
    
    dh_strucs : list 
    list of structures ordered as stored in the pw_data_matrix
    '''

    # set of shared dihedral angles for each structure 
    raw_dihedrals = list()
    dihedral_strucs = list()

    # iterate through the structural models
    if verbose: 
        print("Calculating the dihedral angles...")
    for i,struc in enumerate(structure_list): 

        # parse the pdb files
        if verbose: 
            print(f"Attempting to calculate for {struc}")
        ppdb = PandasPdb().read_pdb(struc)
        ppdb.df['ATOM'] = ppdb.df['ATOM'].loc[(ppdb.df['ATOM']['residue_number'] >= resnum_bounds[0]) & 
                                              (ppdb.df['ATOM']['residue_number'] <= resnum_bounds[1])]
        if np.unique(ppdb.df['ATOM']['residue_number'].values).shape[0] != (resnum_bounds[1] - resnum_bounds[0] + 1): 
            if verbose: 
                print(f"Skipping {struc}; insufficient atoms!")
            continue
        
        raw_dihedrals.append(calculate_backbone_dihedrals(ppdb=ppdb, 
                                                 resnum_bounds=resnum_bounds, 
                                                 no_psi=no_psi, 
                                                 no_omega=no_omega, 
                                                 no_phi=no_phi, 
                                                 verbose=verbose
                                                 )
                    )
        dihedral_strucs.append(struc)

    raw_dihedrals = np.array(raw_dihedrals).reshape(len(dihedral_strucs), -1)
    
    # save the results of the calculation as a np array if desired 
    if save: 
        with open('dihedral_data_matrix.npy', 'wb') as f: 
            np.save(f, raw_dihedrals)

    return raw_dihedrals, dihedral_strucs

def calculate_pw_transformed_loadings(raw_pw_loading, resnum_bounds): 
    '''
    Calculates a transformed loading from a raw loading of pairwise distance features to account 
    for all pairings of residues. 

    Returns a transformed loading. 

    Parameters: 
    -----------
    raw_pw_loading : array_like
    array of raw loading from PCA

    Returns: 
    --------
    transformed_loading : array_like, (N/2,)
    array of transformed loading summing absolute value contributions involving each residue for 
    each principal component 
    '''
    
    # initialize array to store the contributions 
    transformed_loading = np.zeros(resnum_bounds[1]-resnum_bounds[0]+1)
    
    # create array of residue combos 
    pw_combos = np.array(list(combinations(np.arange(resnum_bounds[0], resnum_bounds[1]+1), 2)))
    
    # iterate through the pairs and store contributions in both (since order does not matter for contributions)
    for i,combo in enumerate(pw_combos): 
        
        # access the residues and add contributions for both contributors 
        transformed_loading[combo[0]-resnum_bounds[0]] += np.abs(raw_pw_loading[i])
        transformed_loading[combo[1]-resnum_bounds[0]] += np.abs(raw_pw_loading[i])
        
    return transformed_loading

def generate_pw_matrix(structure_list, resnum_bounds, save=False, verbose=False): 
    '''
    Extracts and returns a data matrix of (observations x features) with the given structures as observations
    and the pairwise distances between alpha carbon (CA) atoms as features. Cannot handle missing
    coordinates and skips structures with missing CA atoms within the given residue numbers. 
    
    Parameters:
    -----------
    structure_list : array_like 
    array containing the file paths to PDB structures

    resnum_bounds : tuple
    tuple containing the minimum and maximum (inclusive) residue number values

    save : boolean, optional 
    indicator to save results once determined

    verbose : boolean, optional 
    indicator for verbose output

    Returns: 
    --------
    pw_data_matrix : array_like 
    array containing pairwise distances between desired CA atoms for all given structures, 
    excluding structures missing desired atoms 

    pw_strucs : list 
    list of structures ordered as stored in the pw_data_matrix
    '''

    # initialize an array to store the pairwise distances and structures 
    pw_dist = list()
    pw_strucs = list()

    # set of coordinates for all structures 
    if verbose: 
        print("Generating the coordinate set...")
    for i,struc in enumerate(structure_list): 

        # parse the pdb files 
        if verbose: 
            print(f'Attempting to calculate for {struc}')
        ppdb = PandasPdb().read_pdb(struc)
        cas = ppdb.df['ATOM'][(ppdb.df['ATOM']['atom_name'] == 'CA') & 
                              (ppdb.df['ATOM']['residue_number'] >= resnum_bounds[0]) & 
                              (ppdb.df['ATOM']['residue_number'] <= resnum_bounds[1])]

        # check that all pairs of CA atoms are present 
        if cas.shape[0] != (resnum_bounds[1] - resnum_bounds[0] + 1): 
            if verbose: 
                print(f'Skipping {struc}; not all desired CA atoms present!')
            continue
        
        # retrieve the CA coordinate information and calculate pairwise distances
        pw_dist.append(pdist(cas[['x_coord', 'y_coord', 'z_coord']].to_numpy()))
        pw_strucs.append(struc)

    pw_data_matrix = np.array(pw_dist).reshape(len(pw_strucs), -1)

    # save the results of the calculation as a np array if desired 
    if save: 
        with open('pw_data_matrix.npy', 'wb') as f: 
            np.save(f, pw_data_matrix)

    return pw_data_matrix, pw_strucs

def calculate_sa_transformed_loadings(raw_sa_loading, shared_atom_list): 
    '''
    Calculates a transformed loading from a raw loading of shear tensor features. 

    Returns a transformed loading. 

    Parameters: 
    -----------
    raw_sa_loading : array_like
    array of raw loading from PCA

    shared_atom_list : array_like 
    sorted list of shared atoms between all structures used for strain analysis 

    Returns: 
    --------
    transformed_loading : array_like 
    array of transformed loading summing absolute value contributions involving each residue for 
    each principal component
    '''
    
    # first find atomic contributions 
    atomic_contributions = np.sum(np.abs(raw_sa_loading.reshape(-1,3)), axis=1)
    
    # create list of resnums 
    shared_atom_list = np.array(shared_atom_list)
    resnum_list = shared_atom_list[:,0].astype("int64")

    # ensure that the number of atoms is consistent
    assert(resnum_list.shape[0] == atomic_contributions.shape[0])
    
    # find unique residue numbers 
    unq_resnums = np.unique(resnum_list)
    
    # initialize array to store the contributions
    transformed_loading = np.zeros(unq_resnums.shape)
    
    # iterate through residue numbers 
    for i,resnum in enumerate(unq_resnums): 
        
        # access the contributions and sum 
        transformed_loading[i] += np.sum(atomic_contributions[resnum_list == resnum])
        
    return transformed_loading

def generate_strain_matrix(structure_list, reference_pdb, data_type, resnum_bounds, atoms=["N", "C", "CA", "CB", "O"], save=True, verbose=False): 
    '''
    Extracts and returns a data matrix of (observations x features) with the given structures as observations
    and strain tensors, shear tensors, or shear energies. For tensor features, only the off-diagonal 
    elements are included. Cannot handle missing coordinates and skips structures with missing 
    backbone atoms within the given residue numbers. 
    
    Parameters:
    -----------
    structure_list : array_like 
    array containing the file paths to PDB structures

    reference_pdb : string
    file path to the reference PDB structure; this structure can be contained in structure_list

    data_type : string 
    indicator for type of data to build data matrix

    resnum_bounds : tuple
    tuple containing the minimum and maximum (inclusive) residue number values

    atoms : array_like, optional 
    array containing atoms (residue number and atom name) to be used in analysis 

    save : boolean, optional 
    indicator to save results once determined

    verbose : boolean, optional 
    indicator for verbose output

    Returns: 
    --------
    sa_data_matrix : array_like 
    array containing strain or tensor information for all given structures, excluding structures 
    missing desired atoms 

    sa_strucs : list 
    list of structures ordered as stored in the sa_data_matrix
    '''

    # check if there's already existing pkl files 
    if "strain_dict.pkl" in os.listdir() and "atom_set.pkl" in os.listdir(): 

        strain_dict = pickle.load(open("strain_dict.pkl", "rb"))

    # if not then calculate the strain dictionary 
    else: 

        if verbose: 
            print("There is no existing strain dictionary. Calculating...")
        strain_dict, atom_set = calculate_strain_dict(
            structure_list=structure_list, 
            reference=reference_pdb, 
            resnum_bounds=resnum_bounds, 
            atoms=atoms, 
            save=save, 
            verbose=verbose
        )

    # generate the data matrix 
    sa_data_matrix = list()
    sa_strucs = list()

    if verbose: 
        print(f"Generating desired {data_type} data matrix...")
    # iterate through the keys of the shear dictionary and filtered structures 
    for key in sorted(strain_dict.keys()):

        if verbose: 
            print(f"Attempting to calculate {data_type} matrix for {key}")
        # access the data
        atom_data = strain_dict[key][data_type][strain_dict[key]["atom_idxs"]]

        # get the B-factors and shape the correction scale
        bfacs = np.sqrt(strain_dict[key]["bfacs"][strain_dict[key]["atom_idxs"]])

        # choose the correction to match the strain/shear data selected for analysis
        if data_type == "sheart" or data_type == "straint": 
            correction = np.hstack([bfacs[:,None], bfacs[:,None], bfacs[:,None]]).flatten()
            processed = np.array([tensor[np.triu_indices(3,1)] for tensor in atom_data]).flatten() # off diagonals

        elif data_type == "sheare":
            correction = bfacs
            processed = np.array(atom_data)

        else: 
            ValueError("Must be sheare, sheart, or straint")

        # apply the coorection and store the data
        processed /= correction 
        sa_data_matrix.append(processed)
        sa_strucs.append(key)

    return np.array(sa_data_matrix), sa_strucs

def load_strain_matrix(strain_pkl, data_type): 
    '''
    Loads the strain analysis data matrix using an existing strain_dict (pickle file) and atom_set
    (pickle file) for the supplied data type. 

    Parameters: 
    -----------

    strain_pkl : pathToDataBase
    file path to the desired strain_dict pickle file 

    data_type : string 
    indicator for type of data to build data matrix

    Returns: 
    --------
    sa_data_matrix : array_like 
    array containing strain or tensor information for all given structures, excluding structures 
    missing desired atoms 

    sa_strucs : list 
    list of structures ordered as stored in the sa_data_matrix
    '''
        
    strain_dict = pickle.load(open(f"{strain_pkl}", "rb"))

    # generate the data matrix and structure list 
    sa_data_matrix = list()
    sa_strucs = list()

    print(f"Generating desired {data_type} data matrix...")
    # iterate through the keys of the shear dictionary and filtered structures 
    for key in strain_dict.keys():

        # access the data
        atom_data = strain_dict[key][data_type][strain_dict[key]["atom_idxs"]]

        # get the B-factors and shape the correction scale
        bfacs = np.sqrt(strain_dict[key]["bfacs"][strain_dict[key]["atom_idxs"]])

        # choose the correction to match the strain/shear data selected for analysis
        if data_type == "sheart" or data_type == "straint": 
            correction = np.hstack([bfacs[:,None], bfacs[:,None], bfacs[:,None]]).flatten()
            processed = np.array([tensor[np.triu_indices(3,1)] for tensor in atom_data]).flatten() # off diagonals

        elif data_type == "sheare":
            correction = bfacs
            processed = np.array(atom_data)

        else: 
            ValueError

        processed /= correction 

        # store the data
        sa_data_matrix.append(processed)
        sa_strucs.append(key)

    return np.array(sa_data_matrix), sa_strucs