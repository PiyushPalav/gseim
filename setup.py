from setuptools import setup, find_packages


setup(
    name='GSEIMIITB',
    version='1.1',
    # license='MIT',
    # author="Piyush Palav",
    # author_email='piyushdpalav@gmail.com',
    packages=find_packages('src'),
    package_dir={'': 'src'},
    url='https://github.com/PiyushPalav/gseim',
    keywords='gseim',
    install_requires=[
          'numpy',
          'matplotlib',
          'psutil',
          'pyyaml'
      ],
   scripts=['src/grc/scripts/run_gseim'],
   data_files=[('bitmaps',['src/grc/gui/icon.png'])
		],
)
