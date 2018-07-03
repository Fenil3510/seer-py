import numpy as np
#import pandas as pd

from datetime import datetime, timedelta, timezone
import sys
import time
import os
import pyedflib
from tkinter import filedialog, messagebox#, StringVar, OptionMenu
import tkinter as tk
import traceback
import multiprocessing
    

def dummpyTK():
    root = tk.Tk()
    root.withdraw()
    root.destroy()
    root = None

def getDir(initialdir=None):
    root = tk.Tk()
    root.withdraw()
    if initialdir is None:
        from pathlib import Path
        initialdir = str(Path.home())
    dirselect = filedialog.Directory(initialdir = initialdir)
#    root.update()
    
    
    root.geometry('0x0+0+0')
    root.deiconify()
    root.lift()
    root.focus_force()
    openDir = dirselect.show()
    root.update()

    root.destroy()
    root = None
    return openDir

def dlData(q, client):
    
    try:
        while True:
            data = q.get()
            if data is None:
                time.sleep(20)
                q.put(None)
                break
            tempData, directory, study, chanGroup, chunk, counter = data
            startTime = datetime.fromtimestamp(tempData.iloc[0,:]['segments.startTime']/1000, tz=timezone.utc)
            startTime += timedelta(hours=int(tempData.iloc[0,:]['segments.timezone']))
            
            fileName = directory + '/' + study + '_' + str(int(counter)).zfill(4) + '_' + chanGroup      
            
            b = ('   -> %s %d' % (fileName, counter) + ''*200)
            sys.stdout.write('\r'+b)
            sys.stdout.flush()
            
            ## Using threads>1 may speed up your downloads, but may also cause issues
            ## on Windows systems. Use Carefully.
            data = client.getLinks(tempData.copy(), threads=5)
            metaData = {}
            if data is not None:
                data.drop(['time', 'id','channelGroups.id','segments.id'], axis=1, inplace=True)
                metaData['sampleRate'] = tempData.iloc[0,:]['channelGroups.sampleRate']
                metaData['upperBound'] = tempData.iloc[0,:]['channelGroups.signalMax']
                metaData['lowerBound'] = tempData.iloc[0,:]['channelGroups.signalMin']
                metaData['exponent'] = tempData.iloc[0,:]['channelGroups.exponent']
                metaData['transducer'] = tempData.iloc[0,:]['channelGroups.name']
            
                makeEdf(fileName, study, startTime, data, **metaData)
                
    except Exception as e:
        print(e)

## make channel headers for edf file (needs work)
def makeChannelHeaders(label, unit='V', sampleRate=256,
                        physicalMax=100, physicalMin=-100,
                        digital_max=32767, digital_min=-32768,
                        transducer='', prefilter=''):
    
    ch_dict = {'label': label, 'dimension': unit, 
       'sample_rate': sampleRate, 'physical_max': physicalMax, 
       'physical_min': physicalMin, 'digital_max': digital_max, 
       'digital_min': digital_min, 'transducer': transducer, 
       'prefilter':prefilter}
    
    return ch_dict


## create edf 
def makeEdf(fileName, pat, startDateTime, df, sampleRate, upperBound, lowerBound,
            transducer, exponent):
    
    channelInfo = []
    dataList = []
    channelNames = df.columns.values.tolist()
    
#    print(df.iloc[:,0].min(), df.iloc[:,0].max(), upperBound, transducer)
    
    for c in range(len(channelNames)):
        cName = str(channelNames[c])
        
        if exponent == -3:
            unit = 'mV'
        elif exponent == -6:
            unit = 'uV'
        else:
            unit = 'V'
        
        ch_dict = makeChannelHeaders(cName,
                                     unit=unit,
                                     sampleRate=sampleRate,
                                     physicalMax=upperBound,
                                     physicalMin=lowerBound,
                                     transducer=transducer + ' ' + channelNames[c])
        
        channelInfo.append(ch_dict)
        dataList.append(np.asarray(df.iloc[:,c].copy())*10**-exponent)
        

    f = pyedflib.EdfWriter(fileName + '.edf', len(channelNames),
                           file_type=pyedflib.FILETYPE_EDF)
    f.setStartdatetime(startDateTime)
    
    f.setGender('')
    f.setPatientName(pat)
    f.setSignalHeaders(channelInfo)
    f.writeSamples(dataList)
    f.close()
    del f


if __name__ == '__main__':
    if sys.platform.startswith('win'):
        # On Windows calling this function is necessary.
        multiprocessing.freeze_support()

    try:
        import seerpy
        client = seerpy.SeerConnect()
        
        
        q = multiprocessing.Queue(9999)
        procs = [multiprocessing.Process(target=dlData, args=(q,client)) for i in range(5)]
#        for p in procs: p.daemon = False
        for p in procs: p.start()
        
        study = input('Study to Download: ')
        studies = [study]
        
        dummpyTK()
        path = getDir() + '/'
    
        for study in studies:
            directory = path + study
            try:
                os.stat(directory)
            except:
                os.mkdir(directory)  
            
            print('\nStudy: ', study)
            print('  Retrieving metadata...')
    
            allData = None
            allData = client.createMetaData(study)
            allData = allData.sort_values('segments.startTime')
    
            numFiles = len(allData['segments.startTime'].unique())
            print('  Downloading %d file(s)...' % numFiles)
            print('\r')
            counter = 1
            
            tempData = []
            for chunk in allData['segments.startTime'].unique():
                chunkData = allData[allData['segments.startTime']==chunk].copy()
                for chanGroup in chunkData['channelGroups.name'].unique():
                    q.put([chunkData[chunkData['channelGroups.name']==chanGroup].copy(), directory, study, chanGroup, chunk, counter])
                counter += 1
#                if counter>2:
#                    break
                    
            q.put(None)
            for p in procs: p.join()

            
    except Exception as e:
        with open('errors.log', 'w') as er:
            er.write(str(e))
            er.write(traceback.format_exc())
        for p in procs: p.terminate()
        raise
    for p in procs: p.terminate()