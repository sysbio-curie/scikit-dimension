[![Build Status](https://travis-ci.com/j-bac/scikit-dimension.svg?branch=master)](https://travis-ci.com/j-bac/scikit-dimension)
[![Build status](https://ci.appveyor.com/api/projects/status/tvumlfad69g6ap3u/branch/master?svg=true)](https://ci.appveyor.com/project/j-bac/scikit-dimension/branch/master)
[![codecov](https://codecov.io/gh/j-bac/scikit-dimension/branch/master/graph/badge.svg)](https://codecov.io/gh/j-bac/scikit-dimension)
[![CircleCI](https://circleci.com/gh/j-bac/scikit-dimension/tree/master.svg?style=shield)](https://circleci.com/gh/j-bac/scikit-dimension/tree/master)
[![Documentation Status](https://readthedocs.org/projects/scikit-dimension/badge/?version=latest)](https://scikit-dimension.readthedocs.io/en/latest/?badge=latest)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/j-bac/scikit-dimension.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/j-bac/scikit-dimension/context:python)
[![GitHub license](https://img.shields.io/github/license/j-bac/scikit-dimension)](https://github.com/j-bac/scikit-dimension/blob/master/LICENSE)


# scikit-dimension

scikit-dimension is a (work-in-progress /!\\) Python module for intrinsic dimension estimation built according to the [scikit-learn](https://github.com/scikit-learn/scikit-learn) API and distributed under the 3-Clause BSD license.

### Installation

Using pip:
```bash
pip install git+https://github.com/sysbio-curie/scikit-dimension.git
```

From source:
```bash
git clone https://github.com/sysbio-curie/scikit-dimension
cd scikit-dimension
pip install .
```

### Quick start

Local and global estimators can be used in this way:

```python
import skdim
import numpy as np

#generate data : np.array (n_points x n_dim). Here a uniformly sampled 5-ball embedded in 10 dimensions
data = np.zeros((1000,10))
data[:,:5] = skdim.gendata.hyperBall(n_points = 1000, n_dim = 5, radius = 1, random_state = 0)

#fit an estimator of global intrinsic dimension (gid)
danco = skdim.gid.DANCo().fit(data)
#fit an estimator of local intrinsic dimension (lid): local estimators assume input data comes from a local data neighborhood
fishers = skdim.lid.FisherS().fit(data)
#fit a global or local estimator in k-nearest-neighborhoods of each point:
lpca_pw = skdim.asPointwise(data = data,
                            class_instance = skdim.lid.lPCA(),
                            n_neighbors = 100,
                            n_jobs = 1)

#get estimated intrinsic dimension
print(danco.dimension_, fishers.dimension_, np.mean(lpca_pw))
```

Please refer to the [documentation](https://scikit-dimension.readthedocs.io) for detailed API and examples.

### Credits and links to original implementations:

##### R
- Kerstin Johnsson
https://cran.r-project.org/web/packages/intrinsicDimension/index.html

- Hideitsu Hino
https://cran.r-project.org/web/packages/ider/index.html

#### MATLAB
- Gabriele Lombardi https://fr.mathworks.com/matlabcentral/fileexchange/40112-intrinsic-dimensionality-estimation-techniques
- Miloš Radovanović https://perun.pmf.uns.ac.rs/radovanovic/tle/

#### C++ TwoNN
- Elena Facco https://github.com/efacco/TWO-NN

#### Python TwoNN 
- Francesco Mottes https://github.com/fmottes/TWO-NN 
and my modified fork https://github.com/j-bac/TWO-NN
