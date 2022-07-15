from setuptools import setup, find_packages


setup(
    name='GSEIMIITB',
    version='1.0',
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
)
