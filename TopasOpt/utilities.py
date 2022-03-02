"""
Supporting classes and functions that don't belong anywhere else in particular
"""
from bayes_opt.logger import JSONLogger
import sys
import os
sys.path.append('.')
# from WaterTankAnalyser import WaterTankData
# import numpy as np
# from matplotlib import pyplot as plt
import os, sys
import logging
import numpy as np
import topas2numpy as tp
import matplotlib.pyplot as plt
from scipy.interpolate import RegularGridInterpolator
from scipy.stats import linregress
from pathlib import Path
plt.interactive(False)

logging.basicConfig(level=logging.WARNING)

class bcolors:
    """
    This is just here to enable me to print pretty colors to the linux terminal
    """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class FigureSpecs:
    """
    Thought this might be the easiest way to ensure universal parameters accross all figures
    """
    LabelFontSize = 14
    TitleFontSize = 16
    Font = 'serif'
    AxisFontSize = 14


class newJSONLogger(JSONLogger):
    """
    To avoid the annoying behaviour where the bayesian logs get deleted on restart.
    Thanks to: https://github.com/fmfn/BayesianOptimization/issues/159
    """
    def __init__(self, path):
        self._path = None
        super(JSONLogger, self).__init__()
        self._path = path if path[-5:] == ".json" else path + ".json"


class WaterTankData:
    """
    Read in and analyse a series of topas scoring files in a rectangular phantom (the water tank).
    There are two ways you might want to use this:

    1. Analyse a single dose file
    2. Analyse multiple dose files all on the same scoring grid

    The main attribute is the 'DoseCube' array. This is the agregate of all the input files. If you
    only put one file in, then this is simply the agregate of that single file.
    A number of plotting routines are already provided which operate on this array, but if you need to you can use
    ExtractDataFromDoseCube to generate any additional data from it.

    Basic use::

        home = os.path.expanduser("~")
        AnalysisPath = home + '/Dropbox (Sydney Uni)/Projects/PhaserSims/topas/Paper_7mm_all/Results/'
        FileToAnalyse = GetAllBinFiles(AnalysisPath)
        Dose = WaterTankData(AnalysisPath, FileToAnalyse, MirrorData=True)
        Dose.Plot_DosePlanes()
        # extract some additional data from agregate dose cube, XY plane for example:
        [Xpts, Ypts] = np.meshgrid(Dose.x, Dose.y)
        Zpts = Dose.PhantomSizeZ * np.ones(Xpts.shape)
        XY_data = Dose.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)

    """

    def __init__(self, AnalysisPath, FileToAnalyse, AbsDepthDose=False):
        """
        :param AnalysisPath: Path where files are located
        :type AnalysisPath: string
        :param FileToAnalyse: Can be either a single file or a list of tiles
        :type FileToAnalyse: list or string
        :param AbsDepthDose: If True, plots are in dose, if False they are normalised to Dmax
        :type AbsDepthDose: Boolean, optional
        """

        self.AnalysisPath = AnalysisPath
        self.FileToAnalyse = FileToAnalyse
        # the below lists all get appended to as data is read in
        self.Xangles = []
        self.Yangles = []
        self.MaxDoseAtIsoplane = []
        self.MaxDoseAtIsoplaneGauss = []
        self.BeamletWidthsManual = []
        self.BeamletWidthsGauss = []
        self.CrossChannelLeakageRatio = []
        self.DmaxToD100 = []
        self.RelOutOfFieldSurfDose = []
        self.DosePerCoulomb = []
        self.LegendNames = []
        self.OF = []

        self.ReverseZDirection = True  # True makes the PDDs go in the normal direction
        self.AbsDepthDose = AbsDepthDose  # if true, dose is plotted instead of percentage

        # these settings keep track of whether certain warnigs have already been thrown
        self.DistanceUnitMessage = False  # just to keeep track of messages (only want to throw once)
        self.MirrorWarning = False  # just to keeep track of messages (only want to throw once)
        self.UnderflowWarning = False
        self.DoseUnitsWarning = False  # just to keeep track of messages (only want to throw once)

        # set figure specs:

        plt.rc('font', family=FigureSpecs.Font)
        plt.rc('xtick', labelsize=FigureSpecs.AxisFontSize)
        plt.rc('ytick', labelsize=FigureSpecs.AxisFontSize)
        self._ReadDoseFilesIntoDoseCube()
        self.__GenerateDepthDoseData()
        self.__GenerateProfileData()

    def _ReadDoseFilesIntoDoseCube(self):
        """
        read all dose files into an integral 'dose cube' that can be queried later
        """
        self.MultiFileMode = True  # overwrite below if not
        if isinstance(self.FileToAnalyse, str):
            # convert to list so we can use the same read in...
            self.FileToAnalyse = list([self.FileToAnalyse])
            self.MultiFileMode = False

        for file in self.FileToAnalyse:

            self.CurrentFile = file
            # file read in and processing
            FileName, Filetype = os.path.splitext(self.CurrentFile)
            self.LegendNames.append(FileName)

            self.__ReadInDoseFiles()
            self.__ConstructCoordinateSystem()

            # generate the data for plots:
            self.__GenerateDoseCubeData()

    def __ReadInDoseFiles(self):
        """
        read in the dose file using topas2numpy
        """
        try:
            FileLocation = str(Path(self.AnalysisPath) / self.CurrentFile)
            if not os.path.isfile(FileLocation):
                FileLocation = FileLocation + '.bin'
                if not os.path.isfile(FileLocation):
                    logging.error(f'Could not locate file: \n{FileLocation}')
            self.dose = tp.BinnedResult(FileLocation)
            # convert dose units:
            if self.dose.unit == 'Gy':
                DoseConverter = 1e6
                self.dose.unit = '\u03BCGy'
                if not self.DoseUnitsWarning:
                    print(f'converting Gy to {self.dose.unit}')
                    self.DoseUnitsWarning = True
            elif self.dose.unit == 'mGy':
                DoseConverter = 1000
                self.dose.unit = '\u03BCGy'
                if not self.DoseUnitsWarning:
                    print(f'converting mGy to {self.dose.unit}')
            else:
                DoseConverter = 1
                logging.warning('unable to detect dose unit; reading in without conversion')
            self.dose.data['Sum'] = self.dose.data['Sum'] * DoseConverter

        except FileNotFoundError:
            logging.warning(f'{bcolors.FAIL}Could not find one of the input files or file header: {self.CurrentFile}{bcolors.ENDC}\n')
            sys.exit(1)

        if np.max(self.dose.data['Sum'])<1e-16:
            logging.error(f'there is no data in the dose file {FileLocation}')

    def __ConstructCoordinateSystem(self):
        """
        Build a coordinate system based off the dose cube information.
        For multifile mode, the coordinate system is only created the first time this function is called,
        otherwise it checks that the phantom dimensions are the same for subsequent files, and will cause
        an error if not
        """
        # what unit is the file in?
        if self.dose.dimensions[0].unit == 'cm':
            UnitConverter = 10
            if not self.DistanceUnitMessage:
                print('converting cm to mm')
                self.DistanceUnitMessage = True
        elif self.dose.dimensions[0].unit == 'mm':
            UnitConverter = 1
        else:
            UnitConverter = 1
            logging.warning('unit could not be detected, reading in without converion')

        try:
            # if coordinate system does exist, make sure the current file matches it....
            assert self.PhantomSizeX == ((max(self.dose.dimensions[0].get_bin_centers()) + (
                        self.dose.dimensions[0].bin_width / 2)) / 2) * UnitConverter
            assert self.PhantomSizeY == ((max(self.dose.dimensions[1].get_bin_centers()) + (
                        self.dose.dimensions[1].bin_width / 2)) / 2) * UnitConverter
            assert self.PhantomSizeZ == ((max(self.dose.dimensions[2].get_bin_centers()) + (
                        self.dose.dimensions[2].bin_width / 2)) / 2) * UnitConverter
        except AttributeError:
            # If coordinate system doesn't exist, construct it
            self.PhantomSizeX = ((max(self.dose.dimensions[0].get_bin_centers()) + (
                        self.dose.dimensions[0].bin_width / 2)) / 2) * UnitConverter
            self.PhantomSizeY = ((max(self.dose.dimensions[1].get_bin_centers()) + (
                        self.dose.dimensions[1].bin_width / 2)) / 2) * UnitConverter
            self.PhantomSizeZ = ((max(self.dose.dimensions[2].get_bin_centers()) + (
                        self.dose.dimensions[2].bin_width / 2)) / 2) * UnitConverter
            self.CoordOffsetX = self.PhantomSizeX  # assumes that phantom is centered around X/Y
            self.CoordOffsetY = self.PhantomSizeY
            self.CoordOffsetZ = 0
            self.x = (self.dose.dimensions[0].get_bin_centers() * UnitConverter) - self.CoordOffsetX
            self.y = (self.dose.dimensions[1].get_bin_centers() * UnitConverter) - self.CoordOffsetY
            self.z = (self.dose.dimensions[2].get_bin_centers() * UnitConverter) - self.CoordOffsetZ
            self.VoxelSizeX = ((self.PhantomSizeX * 2) / self.dose.dimensions[0].n_bins)
            self.VoxelSizeY = ((self.PhantomSizeY * 2) / self.dose.dimensions[1].n_bins)
            self.VoxelSizeZ = ((self.PhantomSizeZ * 2) / self.dose.dimensions[2].n_bins)

        self.DataSize = np.array([self.x.shape[0], self.y.shape[0], self.z.shape[0]])
        dim_check_ind = self.DataSize < 2  # check for singleton dimensions
        if dim_check_ind.any():
            # singleton dimensions will be mirrored to recover 3D data
            axes_names = np.array(['X', 'Y', 'Z'])
            logging.warning(f'singletony dimenions detected; expanding data in {axes_names[dim_check_ind][0]} to recover 3D')
            if dim_check_ind[0]:
                self.x = np.array([-self.x, self.x])
            elif dim_check_ind[1]:
                y_original = self.y[0]
                self.y = np.array([y_original - self.PhantomSizeY ,y_original+ self.PhantomSizeY ])
            elif dim_check_ind[2]:
                self.z = np.array([-self.z, self.z])

    def __GenerateDoseCubeData(self):
        """
        Read in all the data into a dose cube so we can query it later

        at the moment, this is done without interpolation, so there is an explicit assumption
        that each read in file has the same coordinate system (which is true for every use case I can currently envisage)
        """
        try:
            test = self.DoseCube
        except AttributeError:
            # the first time this function is called the data won't exist yet so it must be created
            self.DoseCube = np.zeros([self.x.size, self.y.size, self.z.size])
        Dose3D = self.dose.data['Sum']
        if (self.DataSize < 2).any():
            # we also need to expand the dimensinos
            if self.DataSize[0] < 2:
                Dose3D = np.stack([Dose3D.squeeze(),Dose3D.squeeze()], 0)
            elif self.DataSize[1] < 2:
                Dose3D = np.stack([Dose3D.squeeze(),Dose3D.squeeze()], 1)
            elif self.DataSize[2] < 2:
                Dose3D = np.stack([Dose3D.squeeze(),Dose3D.squeeze()], 2)
        self.DoseCube = np.add(self.DoseCube, Dose3D)

    def __GenerateDepthDoseData(self):
        """
        Interpolate depth dose data from current dose cube
        """
        # get logical array for central axis...
        Zpts_dd = self.z
        Xpts_dd = np.zeros(Zpts_dd.shape)
        Ypts_dd = np.zeros(Zpts_dd.shape)
        self.DepthDose  = self.ExtractDataFromDoseCube(Xpts_dd, Ypts_dd, Zpts_dd)

        if not self.AbsDepthDose:
            # then normalise plots to dmax:
            dmax = np.max(self.DepthDose)
            try:
                self.DepthDose = self.DepthDose * 100 / dmax
            except FloatingPointError:
                logging.warning(f'you seem to have divded by zero for files {self.FileToAnalyse[-1]}, which indicates that there is no actual dose '
                                'in the dose file')

    def __GenerateProfileData(self):
        """
        generate the data for plotting profiles.
        Note that this operates on each beamlet, NOT on the integral Dose Cube data
        """
        Xpts_prof = self.x  # profile over entire X range
        Ypts_prof = np.zeros(Xpts_prof.shape)
        Zpts_prof = self.PhantomSizeZ * np.ones(Xpts_prof.shape)  # at the middle of the water tank
        self.ProfileDose_X = self.ExtractDataFromDoseCube(Xpts_prof, Ypts_prof, Zpts_prof)
        # Y profile
        Ypts_prof = self.y  # profile over entire X range
        Xpts_prof = np.zeros(Ypts_prof.shape)
        Zpts_prof = self.PhantomSizeZ * np.ones(Xpts_prof.shape)
        self.ProfileDose_Y = self.ExtractDataFromDoseCube(Xpts_prof, Ypts_prof, Zpts_prof)

        if not self.AbsDepthDose:
            try:
                self.ProfileDose_X = self.ProfileDose_X * 100/max(self.ProfileDose_X)
                self.ProfileDose_Y = self.ProfileDose_Y * 100 / max(self.ProfileDose_Y)
            except FloatingPointError:
                logging.warning(f'you seem to have divded by zero for files {self.FileToAnalyse[-1]}, which indicates that there is no actual dose '
                                'in the dose file')

    # Public methods:

    def ExtractDataFromDoseCube(self, Xpts, Ypts, Zpts):
        """
        Extract data from the dose cube at positions Xpts, Ypts, Zpts
        Each of these is an array or list, and they must be the same shape (they can be of any dimensionality as
        they are flattened inside the function). The data is returned in the same shape as the input points.
        """
        assert Xpts.shape == Ypts.shape == Zpts.shape
        InputShape = Xpts.shape
        # convert to array and flatten
        Xpts = np.array(Xpts).flatten()
        Ypts = np.array(Ypts).flatten()
        Zpts = np.array(Zpts).flatten()

        try:
            test = self.DoseCubeInterpolator
        except AttributeError:
            self.DoseCubeInterpolator = RegularGridInterpolator((self.x, self.y, self.z), self.DoseCube,
                                                                bounds_error=False, fill_value=0)
            # interpolation function
        pts = np.stack([Xpts, Ypts, Zpts])
        pts = pts.T  # take the tranpose to get the dimnesions right
        InterpolatedData = self.DoseCubeInterpolator(pts)
        InterpolatedData = np.reshape(InterpolatedData,InputShape)

        return InterpolatedData

    def Plot_DosePlanes(self, AddColorBar=False):
        """
        Use the DoseCube data to create a plot through each of the cardinal planes.
        """

        fig, (axs1, axs2, axs3) = plt.subplots(nrows=1, ncols=3, figsize=(15, 5))
        # for generating extent in plots:
        dx = (self.x[1] - self.x[0]) / 2.
        dy = (self.y[1] - self.y[0]) / 2.
        dz = (self.z[1] - self.z[0]) / 2.

        #XY data
        extent = [self.x[0] - dx, self.x[-1] + dx, self.y[0] - dy, self.y[-1] + dy]
        [Xpts, Ypts] = np.meshgrid(self.x, self.y)
        Zpts = self.PhantomSizeZ * np.ones(Xpts.shape)
        XY_data = self.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)

        XYim = axs1.imshow(XY_data, extent=extent)
        axs1.set_xlabel('X [mm]', fontsize=FigureSpecs.LabelFontSize)
        axs1.set_ylabel('Y [mm]', fontsize=FigureSpecs.LabelFontSize)

        # ZX
        axs1.set_title('a) XY plane', fontsize=FigureSpecs.TitleFontSize)
        # fig.colorbar(im)

        #ZX data
        extent = [self.x[0] - dx, self.x[-1] + dx, self.z[0] - dz, self.z[-1] + dz]
        [Xpts, Zpts] = np.meshgrid(self.x, self.z)
        Ypts = np.zeros(Xpts.shape)
        ZX_data = self.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)
        # ZX_data = np.flipud(ZX_data)
        ZXim = axs2.imshow(ZX_data, extent=extent)
        axs2.set_xlabel('X [mm]', fontsize=FigureSpecs.LabelFontSize)
        axs2.set_ylabel('Z [mm]', fontsize=FigureSpecs.LabelFontSize)
        #
        axs2.set_title('b) ZX plane', fontsize=FigureSpecs.TitleFontSize)

        #ZY data
        extent = [self.y[0] - dy, self.y[-1] + dy, self.z[0] - dz, self.z[-1] + dz]
        [Ypts, Zpts] = np.meshgrid(self.y, self.z)
        Xpts = np.zeros(Zpts.shape)
        ZY_data = self.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)
        # ZY_data = np.flipud(ZY_data.T)
        ZYim = axs3.imshow(ZY_data, extent=extent)
        axs3.set_xlabel('Y [mm]', fontsize=FigureSpecs.LabelFontSize)
        axs3.set_ylabel('Z [mm]', fontsize=FigureSpecs.LabelFontSize)

        axs3.set_title('c) ZY plane', fontsize=FigureSpecs.TitleFontSize)

        if AddColorBar:
            cbar = fig.colorbar(XYim, ax=axs1)
            cbar.set_label('\u03BCGy')
            cbar = fig.colorbar(ZXim, ax=axs2)
            cbar.set_label('\u03BCGy')
            cbar = fig.colorbar(ZYim, ax=axs3)
            cbar.set_label('\u03BCGy')

        plt.tight_layout()
        plt.show()

    def Plot_DepthDose(self):
        """
        Plot integral depth dose curves of all beamlets
        """
        try:
            test = self.integralPDD_axs
        except AttributeError:
            fig, self.integralPDD_axs = plt.subplots()
        Zpts = self.z
        Xpts = np.zeros(Zpts.shape)
        Ypts = np.zeros(Zpts.shape)
        dose_plot = self.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)
        if self.ReverseZDirection:
            dose_plot = np.flip(dose_plot)
        if not self.AbsDepthDose:
            # then normalise plots to dmax:
            self.DepthDmax = np.max(dose_plot)
            dose_plot = dose_plot * 100 / self.DepthDmax
            self.integralPDD_axs.set_ylabel('Dose [%]', fontsize=FigureSpecs.LabelFontSize)
            self.integralPDD_axs.set_title('Percentage Depth Dose', fontsize=FigureSpecs.TitleFontSize)
        else:
            self.integralPDD_axs.set_ylabel(f'Dose [{self.dose.unit}]', fontsize=FigureSpecs.LabelFontSize)
            self.integralPDD_axs.set_title('Absolute Depth Dose', fontsize=FigureSpecs.TitleFontSize)
        self.integralPDD_axs.plot(self.z, dose_plot,'-o')
        self.integralPDD_axs.grid(True)
        self.integralPDD_axs.set_xlabel('Depth [mm]', fontsize=FigureSpecs.LabelFontSize)
        plt.show()

    def Plot_Profiles(self, dir='X', Zpoints=None):
        """
        Plot profiles through integrated data. Can choose dir='X' or dir='Y'
        You can also optionally pass multiple Z points; otherwise Z is set to the middle of the phantom
        """
        fig, IntProfile_axs = plt.subplots(figsize=(5, 5))
        if Zpoints is None:
            Zpoints = list([self.PhantomSizeZ])
        if not isinstance(Zpoints, list):
            Zpoints = list([Zpoints])
        if not (dir == 'X' or dir == 'Y'):
            logging.warning(f'invalid direction "{dir}" supplied PlotProfiles; valid options are X or Y. Picking X')
            dir = 'X'
        if dir == 'X':
            Xpts = self.x
            Ypts = np.zeros(Xpts.shape)
            AbcissaPlot = Xpts
            AbcissaLabel = 'X [mm]'
        elif dir == 'Y':
            Ypts = self.y
            Xpts = np.zeros(Ypts.shape)
            AbcissaPlot = Xpts
            AbcissaLabel = 'Y [mm]'

        leg_strings = []
        for zpoint in Zpoints:
            Zpts = zpoint * np.ones(Xpts.shape)
            ProfileData = self.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)
            leg_strings.append(f'Z = {zpoint} mm')
            IntProfile_axs.plot(AbcissaPlot, ProfileData, '-x', markersize=4)

        IntProfile_axs.set_xlabel(AbcissaLabel, size=FigureSpecs.LabelFontSize)
        IntProfile_axs.set_title('Beamlet Profiles', size=FigureSpecs.TitleFontSize)
        IntProfile_axs.set_ylabel(f'Dose [{self.dose.unit}]', size=FigureSpecs.LabelFontSize)
        IntProfile_axs.legend(leg_strings)
        IntProfile_axs.grid('True')
        plt.tight_layout()
        plt.show()

    def Plot_XYsurface(self, Zpoints=None):
        """
        Plot XY plots for multiple Z
        if Z = None, a single plot through the middle of the water phantom is produced
        """
        def GetSubplotsObject(Npoints):
            """
            Just returns an appropriate number of subplots and figure shape for the number of plots the user requested
            """
            if Npoints == 1:
                fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(5, 5))
                axs = np.array([axs])  # to make it match other cases
            elif Npoints == 2:
                fig, axs = plt.subplots(nrows=1, ncols=2, figsize=(10, 5))
            elif Npoints == 3:
                fig, axs = plt.subplots(nrows=1, ncols=3, figsize=(15, 5))
            elif Npoints == 4:
                fig, axs = plt.subplots(nrows=2, ncols=2, figsize=(10, 10))
            elif Npoints == 5 or Npoints == 6:
                fig, axs = plt.subplots(nrows=3, ncols=3, figsize=(15, 10))
            else:
                logging.error("Too many Zpoints requested! you've ruined everything by being greedy!")
                sys.exit(1)
            return fig, axs

        if Zpoints is None:
            Zpoints = list([self.PhantomSizeZ])
        if not isinstance(Zpoints, list):
            Zpoints = list([Zpoints])
        figure, axs = GetSubplotsObject(len(Zpoints))
        leg_strings = []

        dx = (self.x[1] - self.x[0]) / 2.
        dy = (self.y[1] - self.y[0]) / 2.
        extent = [self.x[0] - dx, self.x[-1] + dx, self.y[0] - dy, self.y[-1] + dy]
        [Xpts, Ypts] = np.meshgrid(self.x, self.y)

        for (i, zpoint) in enumerate(Zpoints):
            Zpts = zpoint * np.ones(Xpts.shape)
            XY_data = self.ExtractDataFromDoseCube(Xpts, Ypts, Zpts)
            leg_strings.append(f'Z = {zpoint} mm')
            axs_ind = np.unravel_index(i, axs.shape)
            axs[axs_ind].imshow(XY_data, extent=extent)
            axs[axs_ind].set_xlabel('X [mm]', fontsize=FigureSpecs.LabelFontSize)
            axs[axs_ind].set_ylabel('Y [mm]', fontsize=FigureSpecs.LabelFontSize)
            axs[axs_ind].set_title(f'Dose at Z = {zpoint} mm [{self.dose.unit}]', fontsize=FigureSpecs.TitleFontSize)
            plt.tight_layout()
            plt.show()


def compare_multiple_results(BinFiles, abs_dose=False, custom_legend_names=None):
    """
    this produces depth dose and profile plots for a list of topas .bin files.

    :param BinFiles: list of files to analyse
    :type BinFiles: list
    :param abs_dose: % dose (False) or absolute dose (True)
    :type abs_dose: boolean, optional
    :param custom_legend_names: if passed, this list will be used for legend. If not, file names will be used.
    :type custom_legend_names: list, optional
    """

    LineStyles = ['C0-', 'C2--', 'C3:', 'C4-.']
    fig, axs = plt.subplots(ncols=2, nrows=1, figsize=[10, 5])
    legend_names = []
    for i, bin_file in enumerate(BinFiles):
        [path_name, file_name] = os.path.split(bin_file)
        legend_names.append(file_name)
        WTD = WaterTankData(path_name, file_name, AbsDepthDose=abs_dose)
        # plot the differences:

        PlotStyle = i % np.shape(LineStyles)[0]
        axs[0].plot(WTD.x, WTD.ProfileDose_X, LineStyles[PlotStyle], linewidth=2)
        axs[1].plot(WTD.z, np.flip(WTD.DepthDose), LineStyles[PlotStyle], linewidth=2)

        # sns.lineplot(ax=axs[0], x=WTD.x, y=WTD.ProfileDose_X)
        # sns.lineplot(ax=axs[1], x=WTD.z, y=np.flip(WTD.DepthDose))

    axs[0].set_xlabel('X [mm]', fontsize=FigureSpecs.LabelFontSize)
    axs[0].set_ylabel('Dose [%]', fontsize=FigureSpecs.LabelFontSize)
    axs[0].set_title('a) Dose profiles', fontsize = FigureSpecs.TitleFontSize)
    axs[0].grid()
    axs[1].set_xlabel('Z [mm]', fontsize=FigureSpecs.LabelFontSize)
    axs[1].set_ylabel('Dose [%]', fontsize=FigureSpecs.LabelFontSize)
    axs[1].set_title('b) Depth Dose', fontsize=FigureSpecs.TitleFontSize)
    axs[1].grid()

    if not custom_legend_names:
        axs[1].legend(legend_names, fontsize=FigureSpecs.LabelFontSize)
    else:
        axs[1].legend(custom_legend_names, fontsize=FigureSpecs.LabelFontSize)
    plt.show()


def ReadInLogFile(LogFileLoc):
    """
    Read in a log file and return as a dictionary

    :param LogFileLoc: path to log file
    :type LogFileLoc: string or pathlib.Path
    """

    if not os.path.isfile(LogFileLoc):
        print(f'File not found:\n{LogFileLoc}\nQuitting')
        sys.exit(1)

    file1 = open(LogFileLoc, 'r')
    Lines = file1.readlines()


    LineItteration = 0
    ResultsDict = {}
    for line in Lines:
        try:
            d = {i.split(': ')[0]: i.split(': ')[1] for i in line.split(', ')}
            # remaining keys are the things we want to track
            for key in d.keys():
                if key == 'Best parameter set' or 'length scales' in key:
                    # this is the last line
                    break
                if LineItteration == 0:
                    ResultsDict[key] = []
                ResultsDict[key].append(float(d[key]))
            LineItteration += 1
        except IndexError:
            pass

    return ResultsDict


def PlotLogFile(LogFileLoc):
    """
    This function can be used to plot an existing log file

    This just replicates the functionality in Optimisers.TopasOptBaseClass._Plot_Convergence and it would be
    more elegant to just have one function, but that would take some refactoring.
    """
    ResultsDict = ReadInLogFile(LogFileLoc)
    Itteration = ResultsDict.pop('Itteration')
    OF = ResultsDict.pop('ObjectiveFunction')

    LowestVal = np.ones(np.size(OF)) * OF[0]
    for i, val in enumerate(LowestVal):
        if OF[i] < LowestVal[i]:
            LowestVal[i:] = OF[i]

    fig, axs = plt.subplots(nrows=1, ncols=1, figsize=(10, 5))
    axs.plot(Itteration, LowestVal, '-k', linewidth=2)
    axs.plot(Itteration, OF, 'C6')
    axs.set_xlabel('Itteration number', fontsize=FigureSpecs.LabelFontSize)
    axs.set_ylabel('Objective function', fontsize=FigureSpecs.LabelFontSize)
    axs.grid(True)

    try:
        target_prediction = -1 * np.array(ResultsDict['target_prediction_mean'] )
        target_prediction_std = np.array(ResultsDict['target_prediction_std'])
        axs.plot(Itteration, target_prediction, 'C0')
        axs.fill_between(Itteration,
                         target_prediction + target_prediction_std,
                         target_prediction - target_prediction_std, alpha=0.15, color='C0')
        axs.legend(['Best', 'Actual', 'Predicted', r'$\sigma$'])
    except KeyError:
        # predicted isn't  available for optimisers
        axs.legend(['Best', 'Current'])

    MinValue = np.argmin(OF)
    axs.plot(Itteration[MinValue], OF[MinValue], 'r-x')
    axs.set_title('Convergence Plot', fontsize=FigureSpecs.TitleFontSize)

    try:
        target_prediction = -1 * np.array(ResultsDict.pop('target_prediction_mean'))
        target_prediction_std = np.array(ResultsDict.pop('target_prediction_std'))
        axs.plot(Itteration, target_prediction, 'C0--',linewidth=2)
        axs.fill_between(Itteration,
                            target_prediction + target_prediction_std,
                            target_prediction - target_prediction_std, alpha=0.3, color='C0')
        axs.legend(['Actual', 'Predicted', r'$\sigma$'], fontsize=FigureSpecs.LabelFontSize*1.5)
    except KeyError:
        # predicted isn't always available
        pass


    MinValue = np.argmin(OF)
    axs.plot(Itteration[MinValue], OF[MinValue], 'r-x')
    # axs.set_title('Convergence Plot', fontsize=FigureSpecs.TitleFontSize)
    LegendStrings = ResultsDict.keys()

    plt.show()




