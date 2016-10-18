import printer
import caches
import os
import sys
import importlib
import re
import multiprocessing
import time
import dill

HERE = os.path.abspath(os.path.dirname(__file__))

def test(testName, module = ""):
	fileName = _getFileName(testName)
	filePath = _getFilePath(testName)
	if filePath not in sys.path:
		sys.path.append(filePath)

	testFileName = fileName[:-3] + "Test.py"
	testFilePath = _getTestDirPath(testFileName, module = module)
	if testFilePath is None:
		printer.displayError("No test found for {}".format(fileName))
		return
	
	if testFilePath not in sys.path:
		sys.path.append(testFilePath)
	
	testModule = importlib.import_module(testFileName[:-3])
	testModule._fileName = os.path.join(filePath, fileName)
	
	_runTests(testModule)

def testModule(module):
	testNames = _getTestNames(module)

	if not testNames:
		printer.displayError("no tests found in module: {}".format(module))
		return

	for testName in testNames:
		test(testName, module = module)
	
def _runTests(testModule):
	def runner(testModule, queue):
		queue.put((False, None, None)) # signal stop timing

		reservedNames = ["before", "after"]
		testCreators = [method for method in testModule.__dict__.values() if callable(method) and method.__name__ not in reservedNames]

		printer.displayTestName(os.path.basename(testModule._fileName))

		if hasattr(testModule, "before"):
			try:
				testModule.before()
			except Exception as e:
				printer.displayError("Something went wrong at setup:\n{}".format(e))
				return

		cachedResults = {}

		# run tests in noncolliding execution order
		for test in _getTestsInExecutionOrder([tc() for tc in testCreators]):
			queue.put((True, test.description(), test.timeout())) # signal start timing, and reset timer
			cachedResults[test] = test.run()
			queue.put((False, None, None)) # signal stop timing

		# print test results in order
		for test in sorted(cachedResults.keys()):
			if cachedResults[test] != None:
				printer.display(cachedResults[test])

		if hasattr(testModule, "after"):
			try:
				testModule.after()
			except Exception as e:
				printer.displayError("Something went wrong at closing:\n{}".format(e))

	q = multiprocessing.Queue()
	p = multiprocessing.Process(target=runner, name="Tester", args=(testModule, q))
	p.start()

	start = time.time()
	isTiming = False
	
	while p.is_alive():
		while not q.empty():
			isTiming, description, timeout = q.get()
			start = time.time()

		if isTiming and time.time() - start > timeout:
			printer.displayError("Timeout ({} seconds) reached during: {}".format(timeout, test.description()))
			p.terminate()
			p.join()
			return
		
		time.sleep(0.1)

def _getTestsInExecutionOrder(tests):
	testsInExecutionOrder = []
	for i, test in enumerate(tests):
		dependencies = _getTestsInExecutionOrder([tc() for tc in test.dependencies()]) + [test]
		testsInExecutionOrder.extend([t for t in dependencies if t not in testsInExecutionOrder])
	return testsInExecutionOrder

def _getTestNames(moduleName):
	moduleName = _backslashToForwardslash(moduleName)
	for (dirPath, dirNames, fileNames) in os.walk(os.path.join(HERE, "tests")):
		dirPath = _backslashToForwardslash(dirPath)
		if moduleName in dirPath:
			return [fileName[:-7] for fileName in fileNames if fileName.endswith(".py") and not fileName.startswith("_")]

def _getTestDirPath(testFileName, module = ""):
	module = _backslashToForwardslash(module)
	testFileName = _backslashToForwardslash(testFileName)
	for (dirPath, dirNames, fileNames) in os.walk(os.path.join(HERE, "tests")):
		if module in _backslashToForwardslash(dirPath) and testFileName in fileNames:
			return dirPath

def _getFileName(completeFilePath):
	fileName = os.path.basename(completeFilePath)
	if not fileName.endswith(".py"):
		fileName += ".py"
	return fileName
	
def _getFilePath(completeFilePath):
	filePath = os.path.dirname(completeFilePath)
	if not filePath:
		filePath = os.path.dirname(os.path.abspath(_getFileName(completeFilePath)))
	return filePath

def _backslashToForwardslash(text):
	return re.sub("\\\\", "/", text)