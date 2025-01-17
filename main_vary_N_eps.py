import community
import networkx as nx
import time
import numpy as np
import multiprocessing
from numpy.random import laplace
from sklearn import metrics
from utils import *
import os


class Run:
    """
    A class that stores information shared between experiments.
    """

    def __init__(self, dataset_name, epsilon, e1, e2, e3, exp_num, mat0, mat0_graph):
        self.dataset_name = dataset_name
        self.epsilon = epsilon
        self.e1 = e1
        self.e2 = e2
        self.e3 = e3
        self.exp_num = exp_num
        self.mat0 = mat0
        self.mat0_graph = mat0_graph


def run_experiment(exper: int, run: Run):
    print("-----------N=%d,exper=%d/%d-------------" % (run.n1, exper + 1, run.exp_num))

    # Community Initialization
    mat1_pvarr1 = community_init(run.mat0, run.mat0_graph, epsilon=run.e1, nr=run.n1)

    part1 = {}
    for i in range(len(mat1_pvarr1)):
        part1[i] = mat1_pvarr1[i]

    # Community Adjustment
    mat1_par1 = comm.best_partition(run.mat0_graph, part1, epsilon_EM=run.e2)
    mat1_pvarr = np.array(list(mat1_par1.values()))

    # Information Extraction
    mat1_pvs = []
    for i in range(max(mat1_pvarr) + 1):
        pv1 = np.where(mat1_pvarr == i)[0]
        pvs = list(pv1)
        mat1_pvs.append(pvs)

    comm_n = max(mat1_pvarr) + 1

    ev_mat = np.zeros([comm_n, comm_n], dtype=np.int64)

    # edge vector
    for i in range(comm_n):
        pi = mat1_pvs[i]
        ev_mat[i, i] = np.sum(run.mat0[np.ix_(pi, pi)])
        for j in range(i + 1, comm_n):
            pj = mat1_pvs[j]
            ev_mat[i, j] = int(np.sum(run.mat0[np.ix_(pi, pj)]))
            ev_mat[j, i] = ev_mat[i, j]

    ga = get_uptri_arr(ev_mat, ind=1)
    ev_lambda = 1 / run.e3

    ga_noise = ga + laplace(0, ev_lambda, len(ga))

    ga_noise_pp = FO_pp(ga_noise)
    ev_mat = get_upmat(ga_noise_pp, comm_n, ind=1)

    # degree sequence
    dd_s = []
    dd_lam = 2 / run.e3

    for i in range(comm_n):
        dd1 = run.mat0[np.ix_(mat1_pvs[i], mat1_pvs[i])]
        dd1 = np.sum(dd1, 1)

        dd1 = (dd1 + laplace(0, dd_lam, len(dd1))).astype(int)
        dd1 = FO_pp(dd1)
        dd1[dd1 < 0] = 0
        dd1[dd1 >= len(dd1)] = len(dd1) - 1

        dd1 = list(dd1)
        dd_s.append(dd1)

    # Graph Reconstruction
    mat0_node = run.mat0_graph.number_of_nodes()
    mat2 = np.zeros([mat0_node, mat0_node], dtype=np.int8)
    for i in range(comm_n):
        # Intra-community
        dd_ind = mat1_pvs[i]
        dd1 = dd_s[i]
        mat2[np.ix_(dd_ind, dd_ind)] = generate_intra_edge(dd1)

        # Inter-community
        for j in range(i + 1, comm_n):
            ev1 = ev_mat[i, j]
            pj = mat1_pvs[j]
            if ev1 > 0:
                c1 = np.random.choice(pi, ev1)
                c2 = np.random.choice(pj, ev1)
                for ind in range(ev1):
                    mat2[c1[ind], c2[ind]] = 1
                    mat2[c2[ind], c1[ind]] = 1

    mat2 = mat2 + np.transpose(mat2)
    mat2 = np.triu(mat2, 1)
    mat2 = mat2 + np.transpose(mat2)
    mat2[mat2 > 0] = 1

    mat2_graph = nx.from_numpy_array(mat2, create_using=nx.Graph)

    # save the graph
    # file_name = './result/' +  'PrivGraph_%s_%.1f_%d.txt' %(dataset_name,epsilon,exper)
    # write_edge_txt(mat2,mid,file_name)

    mat2_par = community.best_partition(mat2_graph)
    mat2_mod = community.modularity(mat2_par, mat2_graph)

    mat2_cc = nx.transitivity(mat2_graph)

    mat2_degree = np.sum(mat2, 0)
    mat2_deg_dist = np.bincount(np.int64(mat2_degree))  # degree distribution

    mat2_evc = nx.eigenvector_centrality(mat2_graph, max_iter=10000)
    mat2_evc_a = dict(sorted(mat2_evc.items(), key=lambda x: x[1], reverse=True))
    mat2_evc_ak = list(mat2_evc_a.keys())
    mat2_evc_val = np.array(list(mat2_evc_a.values()))

    mat2_diam = cal_diam(mat2)

    # calculate the metrics
    # clustering coefficent
    cc_rel = cal_rel(run.mat0_cc, mat2_cc)

    # degree distribution
    deg_kl = cal_kl(run.mat0_deg_dist, mat2_deg_dist)

    # modularity
    mod_rel = cal_rel(run.mat0_mod, mat2_mod)

    # NMI
    labels_true = list(run.mat0_par.values())
    labels_pred = list(mat2_par.values())
    nmi = metrics.normalized_mutual_info_score(labels_true, labels_pred)

    # Overlap of eigenvalue nodes
    evc_overlap = cal_overlap(run.mat0_evc_ak, mat2_evc_ak, np.int64(0.01 * mat0_node))

    # MAE of EVC
    evc_MAE = cal_MAE(run.mat0_evc_val, mat2_evc_val, k=run.evc_kn)

    # diameter
    diam_rel = cal_rel(run.mat0_diam, mat2_diam)

    # print('Nodes=%d,Edges=%d,nmi=%.4f,cc_rel=%.4f,deg_kl=%.4f,mod_rel=%.4f,evc_overlap=%.4f,evc_MAE=%.4f,diam_rel=%.4f' \
    #     %(mat2_node,mat2_edge,nmi,cc_rel,deg_kl,mod_rel,evc_overlap,evc_MAE,diam_rel))

    data_col = [
        run.epsilon,
        exper,
        run.n1,
        nmi,
        evc_overlap,
        evc_MAE,
        deg_kl,
        diam_rel,
        cc_rel,
        mod_rel,
    ]
    col_len = len(data_col)
    data_col = np.array(data_col).reshape(1, col_len)

    return pd.DataFrame(data_col, columns=run.cols)


def main_vary_N(
    dataset_name="Chamelon",
    epsilon=2,
    e1_r=1 / 3,
    e2_r=1 / 3,
    N_List=[10, 20],
    exp_num=10,
    save_csv=False,
    mat0=None,
    mat0_graph=None,
):
    res_path = "./our_results"
    save_name = (
        res_path
        + "/"
        + "%s_%.2f_%.2f_%.2f_%d.csv" % (dataset_name, epsilon, e1_r, e2_r, exp_num)
    )

    # check if we already ran and saved this run. If so, do nothing.
    if save_csv and os.path.exists(save_name):
        return

    t_begin = time.time()

    data_path = "./data/" + dataset_name + ".txt"

    if mat0 is None:
        mat0, mid = get_mat(data_path)

    # original graph
    if mat0_graph is None:
        mat0_graph = nx.from_numpy_array(mat0, create_using=nx.Graph)

    e3_r = 1 - e1_r - e2_r

    # store data for this run in an object for multiple processes to read from
    run = Run(
        dataset_name,
        epsilon,
        e1_r * epsilon,
        e2_r * epsilon,
        e3_r * epsilon,
        exp_num,
        mat0,
        mat0_graph,
    )

    run.cols = [
        "eps",
        "exper",
        "N",
        "nmi",
        "evc_overlap",
        "evc_MAE",
        "deg_kl",
        "diam_rel",
        "cc_rel",
        "mod_rel",
    ]

    all_data = pd.DataFrame(None, columns=run.cols)

    mat0_node = mat0_graph.number_of_nodes()

    print("Dataset:%s" % (dataset_name))
    print("Node number:%d" % (mat0_node))
    print("Edge number:%d" % (mat0_graph.number_of_edges()))
    print("epsilon:%.2f" % (epsilon))
    print("e1:%.2f" % (e1_r))
    print("e2:%.2f" % (e2_r))
    print("e3:%.2f" % (e3_r))

    run.mat0_par = community.best_partition(mat0_graph)

    mat0_degree = np.sum(mat0, 0)
    run.mat0_deg_dist = np.bincount(np.int64(mat0_degree))  # degree distribution

    run.mat0_evc = nx.eigenvector_centrality(mat0_graph, max_iter=10000)
    run.mat0_evc_a = dict(
        sorted(run.mat0_evc.items(), key=lambda x: x[1], reverse=True)
    )
    run.mat0_evc_ak = list(run.mat0_evc_a.keys())
    run.mat0_evc_val = np.array(list(run.mat0_evc_a.values()))
    run.evc_kn = np.int64(0.01 * mat0_node)

    run.mat0_diam = cal_diam(mat0)

    run.mat0_cc = nx.transitivity(mat0_graph)

    run.mat0_mod = community.modularity(run.mat0_par, mat0_graph)

    for ni in range(len(N_List)):
        ti = time.time()

        run.n1 = N_List[ni]

        num_processes = multiprocessing.cpu_count()

        # Using Pool to parallelize the execution of the function
        with multiprocessing.Pool(processes=num_processes) as pool:
            results = pool.starmap(run_experiment, zip(range(exp_num), [run] * exp_num))

            for res in results:
                all_data = all_data.append(res)

        print("all_index=%d/%d Done.%.2fs\n" % (ni + 1, len(N_List), time.time() - ti))

    if save_csv == True:
        if not os.path.exists(res_path):
            os.mkdir(res_path)

        all_data.to_csv(save_name+"2", index=False, sep=",")

    print("-----------------------------")

    print("dataset:", dataset_name)

    print("epsilon=", epsilon)
    print("all_N=", N_List)
    print("All time:%.2fs" % (time.time() - t_begin))


def experiment_using_epsilon(epsilon: float):
    # set the dataset
    # 'Facebook', 'CA-HepPh', 'Enron'
    dataset_name = 'Congress'
    
    # set the number of experiments
    exp_num = 10

    if epsilon <= 1.0:
        # larger communities for smaller budgets
        N_List = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
    else:
        N_List = [5, 10, 15, 20, 25, 30, 35]

    for e1_ind in range(1, 9):
        e1_r = e1_ind / 10
        for e2_ind in range(1, 9):
            e2_r = e2_ind / 10
            if e1_ind + e2_ind < 10:
                # run the function
                main_vary_N(
                    dataset_name=dataset_name,
                    epsilon=epsilon,
                    e1_r=e1_r,
                    e2_r=e2_r,
                    N_List=N_List,
                    exp_num=exp_num,
                    save_csv=True,
                )


if __name__ == "__main__":
    # set the privacy budget
    epsilon_list = [0.5, 2.0, 3.5]

    for epsilon in epsilon_list:
        experiment_using_epsilon(epsilon=epsilon)
