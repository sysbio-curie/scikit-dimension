from sklearn.base import BaseEstimator
from sklearn.utils.validation import check_array

import numba as nb
import numpy as np
import math
import sklearn.decomposition as sk
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')
from scipy.special import gammainc
from scipy.special import lambertw
from matplotlib import pyplot as plt
import scipy.io
from _commonfuncs import randsphere


class FisherS(BaseEstimator):
    """
    Intrinsic dimension estimation using the FisherS algorithm.
    
    -----------
    Attributes
    ConditionalNumber : - a positive real value used to select the top
            princinpal components. We consider only PCs with eigen values
            which are not less than the maximal eigenvalue divided by
            ConditionalNumber Default value is 10.
    ProjectOnSphere :  a boolean value indicating if projecting on a
            sphere should be performed. Default value is true.
    alphas : 2D np.array, float
        A row vector of floats, with alpha range, the values must be given increasing
            within (0,1) interval. Default is np.arange(.6,1,.02)[None].
    ProducePlots : bool, default=False
        A boolean value indicating if the standard plots need to be drawn.
    ncomp : bool
        Whether to print number of retained principal components
    limit_maxdim : bool
        Whether to cap estimated maxdim to the embedding dimension
       
    -----------
    Returns
    
    n_alpha : 1D np.array, float
        Effective dimension profile as a function of alpha
    n_single : float
        A single estimate for the effective dimension 
    p_alpha : 2D np.array, float
        Distributions as a function of alpha, matrix with columns corresponding to the alpha values, and with rows corresponding to objects. 
    separable_fraction : 1D np.array, float
        Separable fraction of data points as a function of alpha
    alphas : 2D np.array, float
        Input alpha values    
    -----------
    References
    """
    
    
    def __init__(self, ConditionalNumber = 10, ProjectOnSphere = 1,
                 alphas = np.array([np.arange(.6,1,.02)]), ProducePlots = False, 
                 ncomp = 0,limit_maxdim=False):

        self.ConditionalNumber = ConditionalNumber
        self.ProjectOnSphere = ProjectOnSphere
        self.alphas = alphas
        self.ProducePlots = ProducePlots
        self.ncomp = ncomp
        self.limit_maxdim = limit_maxdim
        
    def fit(self,X):
        """A reference implementation of a fitting function.
        Parameters
        ----------
        X : {array-like}, shape (n_samples, n_features)
            The training input samples.

        Returns
        -------
        self : object
            Returns self.
        """
        
        X = check_array(X, accept_sparse=False)
        
        self.n_alpha_,self.dimension_,self.p_alpha_,self.alphas_,self.separable_fraction_,self.Xp_ = self._SeparabilityAnalysis(X)
        
        self.is_fitted_ = True
        # `fit` should always return `self`
        return self        


    @staticmethod
    @nb.njit
    def _histc(X, bins):
        map_to_bins = np.digitize(X,bins)
        r = np.zeros((len(X[0,:]),len(bins)))
        for j in range(len(map_to_bins[0,:])):
            for i in map_to_bins[:,j]:
                r[j,i-1] += 1
        return r

    def _preprocessing(self,X,center,dimred,whiten):
        '''
        %preprocessing of the dataset
        %
        %Inputs
        %   X is n-by-d data matrix with n d-dimensional datapoints.
        %   center is boolean. True means subtraction of mean vector.
        %   dimred is boolean. True means applying of dimensionality reduction with
        %       PCA. Number of used PCs is defined by ConditionalNumber argument.
        %   whiten is boolean. True means applying of whitenning. True whiten
        %       automatically caused true dimred.
        %   projectonsphere is boolean. True means projecting data onto unit sphere
        %   varargin contains Name Value pairs. One possible value can be:
        %       'ConditionalNumber' - a positive real value used to select the top
        %           principal components. We consider only PCs with eigen values
        %           which are not less than the maximal eigenvalue divided by
        %           ConditionalNumber Default value is 10. 
        %
        %Outputs:
        %   X is preprocessed data matrix.'''

        #centering
        nobjects = len(X[:,0])
        sampleMean = np.mean(X,axis=0)
        if center:
            X = X-sampleMean
        #dimensionality reduction if requested dimensionality reduction or whitening
        PCAcomputed = 0
        if dimred or whiten:
            pca = sk.PCA()
            u = pca.fit_transform(X)
            v = pca.components_.T
            s = pca.explained_variance_
            PCAcomputed = 1
            sc = s/s[0]
            ind = np.where(sc > 1/self.ConditionalNumber)[0]
            X = X @ v[:,ind]
            if self.ncomp:
                print('%i components are retained using factor %2.2f' %(len(ind),self.ConditionalNumber))

        #whitening
        if whiten:
            X = u[:,ind]
            st = np.std(X,axis=0,ddof=1)
            X = X/st
        # #project on sphere (scale each vector to unit length)
        if self.ProjectOnSphere:
            st = np.sqrt(np.sum(X**2,axis=1))
            st = np.array([st]).T
            X = X/st

        return X    

    
    @staticmethod
    def _probability_inseparable_sphere(alphas,n):
        ''' 
        %probability_inseparable_sphere calculate theoretical probability for point
        %to be inseparable for dimension n
        %
        %Inputs:
        %   alphas is 1-by-d vector of possible alphas. Must be row vector or scalar
        %   n is c-by-1 vector of dimnesions. Must be column vector or scalar.
        %
        %Outputs:
        %   p is c-by-d matrix of probabilities.'''
        p = np.power((1-np.power(alphas,2)),(n-1)/2)/(alphas*np.sqrt(2*np.pi*n))
        return p

    def _checkSeparability(self,xy):
        dxy = np.diag(xy)
        sm = (xy/dxy).T
        sm = sm - np.diag(np.diag(sm))
        sm = sm>self.alphas
        py = sum(sm.T)
        py = py/len(py[0,:])
        separ_fraction = sum(py==0)/len(py[0,:])

        return separ_fraction,py

    def _checkSeparabilityMultipleAlpha(self,data):
        '''%checkSeparabilityMultipleAlpha calculate fraction of points inseparable
        %for each alpha and fraction of points which are inseparable from each
        %point for different alpha.
        %
        %Inputs:
        %   data is data matrix to calculate separability. Each row contains one
        %       data point.
        %   alphas is array of alphas to test separability.
        %
        %Outputs:
        %   separ_fraction fraction of points inseparable from at least one point.
        %       Fraction is calculated for each alpha.
        %   py is n-by-m matrix. py(i,j) is fraction of points which are
        %       inseparable from point data(i, :) for alphas(j).'''


        #Number of points per 1 loop. 20k assumes approx 3.2GB
        nP = 2000
        
        alphas = self.alphas
        #Normalize alphas
        if len(alphas[:,0])>1:
            alphas = alphas.T
        addedone = 0
        if max(self.alphas[0,:])<1:
            alphas = np.array([np.append(alphas,1)])
            addedone = 1

        alphas = np.concatenate([[float('-inf')],alphas[0,:], [float('inf')]])
        
        
        n = len(data)
        counts = np.zeros((n, len(alphas)))
        leng = np.zeros((n, 1))
        for k in range(0,n,nP):
            #print('Chunk +{}'.format(k))
            e = k + nP 
            if e > n:
                e = n
            # Calculate diagonal part, divide each row by diagonal element
            xy = data[k:e, :] @ data[k:e, :].T
            leng[k:e] = np.diag(xy)[:,None]
            xy = xy - np.diag(leng[k:e].squeeze())
            xy = xy / leng[k:e]
            counts[k:e, :] = counts[k:e, :] + self._histc(xy.T, alphas)
            # Calculate nondiagonal part
            for kk in range(0,n,nP):
                #Ignore diagonal part
                if k == kk:
                    continue                         
                ee = kk + nP 
                if ee > n:
                    ee = n

                xy = data[k:e, :] @ data[kk:ee, :].T
                xy = xy / leng[k:e]
                counts[k:e, :] = counts[k:e, :] + self._histc(xy.T, alphas)

        #Calculate cumulative sum
        counts = np.cumsum(counts[:,::-1],axis=1)[:,::-1]

        #print(counts)

        py = counts/(n)
        py = py.T
        if addedone:
            py = py[1:-2,:]
        else:
            py = py[1:-1,:]

        separ_fraction = sum(py==0)/len(py[0,:])

        return separ_fraction, py


    def _dimension_uniform_sphere(self,py):
        '''
        %Gives an estimation of the dimension of uniformly sampled n-sphere
        %corresponding to the average probability of being inseparable and a margin
        %value 
        %
        %Inputs:
        %   py - average fraction of data points which are INseparable.
        %   alphas - set of values (margins), must be in the range (0;1)
        % It is assumed that the length of py and alpha vectors must be of the
        % same.
        %
        %Outputs:
        %   n - effective dimension profile as a function of alpha
        %   n_single_estimate - a single estimate for the effective dimension 
        %   alfa_single_estimate is alpha for n_single_estimate.
        '''
        
        if len(py)!=len(self.alphas[0,:]):
            raise ValueError('length of py (%i) and alpha (%i) does not match'%(len(py),len(self.alphas[0,:])))

        if np.sum(self.alphas <= 0) > 0 or np.sum(self.alphas >= 1) > 0:
            raise ValueError(['"Alphas" must be a real vector, with alpha range, the values must be within (0,1) interval'])

        #Calculate dimension for each alpha
        n = np.zeros((len(self.alphas[0,:])))
        for i in range(len(self.alphas[0,:])):
            if py[i] == 0:
                #All points are separable. Nothing to do and not interesting
                n[i]=np.nan
            else:
                p  = py[i]
                a2 = self.alphas[0,i]**2
                w = np.log(1-a2)
                n[i] = np.real(lambertw(-(w/(2*np.pi*p*p*a2*(1-a2)))))/(-w)

        n[n==np.inf] = float('nan')
        #Find indices of alphas which are not completely separable 
        inds = np.where(~np.isnan(n))[0]
        if len(inds) == 0:
            warnings.warn('All points are fully separable for any of the chosen alphas')
            return n,np.array([np.nan]),np.nan

        #Find the maximal value of such alpha
        alpha_max = max(self.alphas[0,inds])
        #The reference alpha is the closest to 90 of maximal partially separable alpha
        alpha_ref = alpha_max*0.9
        k = np.where(abs(self.alphas[0,inds]-alpha_ref)==min(abs(self.alphas[0,:]-alpha_ref)))[0]
        #Get corresponding values
        alfa_single_estimate = self.alphas[0,inds[k]]
        n_single_estimate = n[inds[k]]

        return n,n_single_estimate,alfa_single_estimate


    def _dimension_uniform_sphere_robust(self,py):
        '''modification to return selected index and handle the case where all values are 0'''
        if len(py)!=len(self.alphas[0,:]):
            raise ValueError('length of py (%i) and alpha (%i) does not match'%(len(py),len(self.alphas[0,:])))

        if np.sum(self.alphas <= 0) > 0 or np.sum(self.alphas >= 1) > 0:
            raise ValueError(['"Alphas" must be a real vector, with alpha range, the values must be within (0,1) interval'])

        #Calculate dimension for each alpha
        n = np.zeros((len(self.alphas[0,:])))
        for i in range(len(self.alphas[0,:])):
            if py[i] == 0:
                #All points are separable. Nothing to do and not interesting
                n[i]=np.nan
            else:
                p  = py[i]
                a2 = self.alphas[0,i]**2
                w = np.log(1-a2)
                n[i] = lambertw(-(w/(2*np.pi*p*p*a2*(1-a2))))/(-w)

        n[n==np.inf] = float('nan')
        #Find indices of alphas which are not completely separable 
        inds = np.where(~np.isnan(n))[0]
        if inds.size==0:
            n_single_estimate = np.nan
            alfa_single_estimate = np.nan
            return n,n_single_estimate,alfa_single_estimate
        else:
            #Find the maximal value of such alpha
            alpha_max = max(self.alphas[0,inds])
            #The reference alpha is the closest to 90 of maximal partially separable alpha
            alpha_ref = alpha_max*0.9
            k = np.where(abs(self.alphas[0,inds]-alpha_ref)==min(abs(self.alphas[0,:]-alpha_ref)))[0]
            #Get corresponding values
            alfa_single_estimate = self.alphas[0,inds[k]]
            n_single_estimate = n[inds[k]]

            return n,n_single_estimate,alfa_single_estimate,inds[k]


    def point_inseparability_to_pointID(self,idx='all_inseparable', force_definite_dim=False, verbose=True):
        '''
        Turn pointwise inseparability probability into pointwise global ID
        Inputs : 
            args : same as SeparabilityAnalysis
            kwargs : 
                idx : int, string
                    int for custom alpha index
                    'all_inseparable' to choose alpha where lal points have non-zero inseparability probability
                    'selected' to keep global alpha selected
                force_definite_dim : bool
                    whether to force fully separable points to take the minimum detectable inseparability value (1/(n-1)) (i.e., maximal detectable dimension)
        '''

        if idx == 'all_inseparable': #all points are inseparable
            selected_idx = np.argwhere(np.all(self.p_alpha!=0,axis=1)).max()
        elif idx == 'selected': #globally selected alpha
            selected_idx = (self.n_alpha==self.n_single).tolist().index(True)   
        elif type(idx) == int:
            selected_idx = idx
        else:
            raise ValueError('unknown idx parameter')

        #select palpha and corresponding alpha
        palpha_selected = self.p_alpha[selected_idx,:]
        alpha_selected = self.alphas[0,selected_idx]


        py=palpha_selected.copy()
        _alphas=np.repeat(alpha_selected,len(palpha_selected))[None]

        if force_definite_dim:
            py[py==0]=1/len(py)

        if len(py)!=len(_alphas[0,:]):
            raise ValueError('length of py (%i) and alpha (%i) does not match'%(len(py),len(_alphas[0,:])))

        if np.sum(_alphas <= 0) > 0 or np.sum(_alphas >= 1) > 0:
            raise ValueError(['"Alphas" must be a real vector, with alpha range, the values must be within (0,1) interval'])

        #Calculate dimension for each alpha
        n = np.zeros((len(_alphas[0,:])))
        for i in range(len(_alphas[0,:])):
            if py[i] == 0:
                #All points are separable. Nothing to do and not interesting
                n[i]=np.nan
            else:
                p  = py[i]
                a2 = _alphas[0,i]**2
                w = np.log(1-a2)
                n[i] = np.real(lambertw(-(w/(2*np.pi*p*p*a2*(1-a2)))))/(-w)

        n[n==np.inf] = float('nan')

        #Find indices of alphas which are not completely separable 
        inds = np.where(~np.isnan(n))[0]
        if verbose:
            print(str(len(inds))+'/'+str(len(py)),'points have nonzero inseparability probability for chosen alpha = '+str(round(alpha_selected,2))+f', force_definite_dim = {force_definite_dim}')
        return n, inds



    def _SeparabilityAnalysis(self,X):
        '''
        %Performs standard analysis of separability and produces standard plots. 
        %
        %Inputs:
        %   X  - is a data matrix with one data point in each row.
        %   Optional arguments in varargin form Name, Value pairs. Possible names:
        %       'ConditionalNumber' - a positive real value used to select the top
        %           princinpal components. We consider only PCs with eigen values
        %           which are not less than the maximal eigenvalue divided by
        %           ConditionalNumber Default value is 10.
        %       'ProjectOnSphere' - a boolean value indicating if projecting on a
        %           sphere should be performed. Default value is true.
        %       'Alphas' - a real vector, with alpha range, the values must be given increasing
        %           within (0,1) interval. Default is [0.6,0.62,...,0.98].
        %       'ProducePlots' - a boolean value indicating if the standard plots
        %           need to be drawn. Default is true.
        %       'ncomp' - bool, whether to print number of retained principal components
        %       'limit_maxdim' bool, whether to cap estimated maxdim to the embedding dimension
        %Outputs:
        %   n_alpha - effective dimension profile as a function of alpha
        %   n_single - a single estimate for the effective dimension 
        %   p_alpha - distributions as a function of alpha, matrix with columns
        %       corresponding to the alpha values, and with rows corresponding to
        %       objects. 
        %   separable_fraction - separable fraction of data points as a function of
        %       alpha
        %   alphas - alpha values
        '''
        npoints = len(X[:,0])
        # Preprocess data
        Xp = self._preprocessing(X,1,1,1)
        # Check separability
        separable_fraction,p_alpha = self._checkSeparabilityMultipleAlpha(Xp)  
        # Calculate mean fraction of separable points for each alpha.
        py_mean = np.mean(p_alpha,axis=1)    
        n_alpha,n_single,alpha_single = self._dimension_uniform_sphere(py_mean)
        
        alpha_ind_selected = np.where(n_single==n_alpha)[0]

        if self.limit_maxdim:
            n_single = np.clip(n_single,None,X.shape[1])

        if self.ProducePlots:
            #Define the minimal and maximal dimensions for theoretical graph with
            # two dimensions in each side
            n_min = np.floor(min(n_alpha))-2;
            n_max = np.floor(max(n_alpha)+0.8)+2;
            if n_min<1:
                n_min = 1

            ns = np.arange(n_min,n_max+1)

            plt.figure()
            plt.plot(self.alphas[0,:],n_alpha,'ko-');plt.plot(self.alphas[0,alpha_ind_selected],n_single,'rx',markersize=16)
            plt.xlabel('\u03B1',fontsize=16); plt.ylabel('Effective dimension',fontsize=16) ; locs, labels = plt.xticks(); plt.show()
            nbins = int(round(np.floor(npoints/200)))

            if nbins<20:
                nbins = 20


            plt.figure()
            plt.hist(p_alpha[alpha_ind_selected,:][0],bins=nbins)
            plt.xlabel('inseparability prob.p for \u03B1=%2.2f'%(self.alphas[0,alpha_ind_selected]),fontsize=16); plt.ylabel('Number of values');plt.show()

            plt.figure()
            plt.xticks(locs,labels);
            pteor = np.zeros((len(ns),len(self.alphas[0,:])))
            for k in range(len(ns)):
                for j in range(len(self.alphas[0,:])):
                    pteor[k,j] = self._probability_inseparable_sphere(self.alphas[0,j],ns[k])

            for i in range(len(pteor[:,0])):
                plt.semilogy(self.alphas[0,:],pteor[i,:],'-',color='r')
            plt.xlim(min(self.alphas[0,:]),1)
            if True in np.isnan(n_alpha):
                plt.semilogy(self.alphas[0,:np.where(np.isnan(n_alpha))[0][0]],py_mean[:np.where(np.isnan(n_alpha))[0][0]],'bo-','LineWidth',3);
            else: 
                plt.semilogy(self.alphas[0,:],py_mean,'bo-','LineWidth',3);

            plt.xlabel('\u03B1'); plt.ylabel('Mean inseparability prob.',fontsize=16);
            plt.title('Theor.curves for n=%i:%i'%(n_min,n_max))
            plt.show()

        return n_alpha,n_single,p_alpha,self.alphas,separable_fraction,Xp