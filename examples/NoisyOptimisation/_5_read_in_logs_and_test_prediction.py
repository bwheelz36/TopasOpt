import numpy as np
from pathlib import Path
from TopasObjectiveFunction import TopasObjectiveFunction
from TopasOpt.utilities import get_all_files
from bayes_opt import BayesianOptimization
from bayes_opt import UtilityFunction
from matplotlib import pyplot as plt
from sklearn.gaussian_process.kernels import Matern, WhiteKernel
import sys
sys.path.insert(0,'../../TopasOpt')
from pathlib import Path
from TopasOpt import Optimisers as to
from bayes_opt.util import load_logs

def plot_objective_function_variability(BoxPlotData, target_predictions, std_predictions):
    figure, axs = plt.subplots()

    try:
        axs.boxplot(BoxPlotData, labels=['n=2e4', 'n=4e4', 'n=5e4', 'n=5e5'],
                    medianprops={'color': 'k'})
    except ValueError:
        print(f'couldnt label boxplots, label length didnt match data')
        axs.boxplot(BoxPlotData, medianprops={'color': 'k'})

    for i, data in enumerate(BoxPlotData.T):
        axs.scatter(np.ones(BoxPlotData.shape[0]) * i + 1, data)
    axs.set_ylabel('OF')
    axs.set_title('Objective function values')
    axs.grid()
    plt.show()

BaseDirectory =  Path(r'Z:\PhaserSims\topas')
optimisation_params = {}
optimisation_params['ParameterNames'] = ['UpStreamApertureRadius','DownStreamApertureRadius', 'CollimatorThickness']
optimisation_params['UpperBounds'] = np.array([3, 3, 40])
optimisation_params['LowerBounds'] = np.array([1, 1, 10])
optimisation_params['start_point'] = np.array([1.14, 1.73, 39.9])
optimisation_params['Nitterations'] = 100
k1 = Matern(length_scale=[3, 0.2, 0.2])
k2 = WhiteKernel()
custom_kernel = k1 + k2
target_predictions = []
std_predictions = []

sims_to_investigate = ['n_particles_20000', 'n_particles_40000',  'n_particles_50000', 'n_particles_500000']
j = 0
for n_particles in [10e3, 20e3, 30e3, 40e3, 50e3]:
    # first, attempt to get the noise estimatation data:
    test_sim_name = f'n_particles_{int(n_particles)}'
    if test_sim_name in sims_to_investigate:
        data_loc = data_dir / sim / 'Results'
        results = get_all_files(data_loc, 'bin')
        iteration = 0

        for result in results:
            objective_value = TopasObjectiveFunction(data_loc, iteration, take_abs=True)
            # note we added a new parameter so we aren't automatically taking absolute values
            of_results[j].append(objective_value)
            iteration += 1


    # update simulation name:
    SimulationName = f'noisy_opt_n_particles_{int(n_particles)}'
    Optimiser = to.BayesianOptimiser(optimisation_params=optimisation_params, BaseDirectory=BaseDirectory,
                                     SimulationName=SimulationName, OptimisationDirectory=SimulationName,
                                     TopasLocation='~/topas38', Overwrite=True, KeepAllResults=True,
                                     custom_kernel=custom_kernel)
    # at this point, we are going to read in the previous logs and update the gaussian process model:
    log_loc = str(BaseDirectory / SimulationName / 'logs' / 'bayes_opt_logs.json')
    load_logs(Optimiser.optimizer, logs=log_loc)
    # and update the gaussian process model:
    Optimiser.optimizer._gp.fit(Optimiser.optimizer._space.params, Optimiser.optimizer._space.target)
    # set up optimal param array
    optimal_params = {'CollimatorThickness': 27, 'DownStreamApertureRadius': 2.5, 'UpStreamApertureRadius': 1.82}
    optimal_params = dict(sorted(optimal_params.items()))  # make sure they are in alphabetical order
    param_array = np.fromiter(optimal_params.values(), dtype=float)
    # predict objective at this values
    predicted_target, predicted_std = Optimiser.optimizer._gp.predict(param_array.reshape(1, -1), return_std=True)
    target_predictions.append(predicted_target)
    std_predictions.append(predicted_std)



