"""Extract the exact input used in the report from the official full-resolution flood.npy."""
import numpy as np
a=np.load('flood.npy',mmap_mode='r')
assert a.shape==(360,1,500,500)
np.savez_compressed('shenzhen_grid.npz',meters=np.asarray(a[:,0,10::20,10::20]))
