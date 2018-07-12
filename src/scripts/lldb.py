import time
import os
import sys
import shlex
import lldb
import threading

listener = None

class RunInBackground(object):
    def __init__(self, timetolive=5):
        self.timetolive = timetolive
        self.start_time = time.time()

    @property
    def canContinue(self):
        return time.time() - self.start_time < self.timetolive

def connect_command(debugger, command, result, internal_dict):
    # These two are passed in by the script which loads us
    connect_url = internal_dict['fruitstrap_connect_url']
    error = lldb.SBError()

    # We create a new listener here and will use it for both target and the process.
    # It allows us to prevent data races when both our code and internal lldb code
    # try to process STDOUT/STDERR messages
    global listener
    listener = lldb.SBListener('iosdeploy_listener')

    listener.StartListeningForEventClass(debugger,
                                            lldb.SBTarget.GetBroadcasterClassName(),
                                            lldb.SBProcess.eBroadcastBitStateChanged | lldb.SBProcess.eBroadcastBitSTDOUT | lldb.SBProcess.eBroadcastBitSTDERR)

    process = lldb.target.ConnectRemote(listener, connect_url, None, error)

    # Wait for connection to succeed
    events = []
    state = (process.GetState() or lldb.eStateInvalid)
    while state != lldb.eStateConnected:
        event = lldb.SBEvent()
        if listener.WaitForEvent(1, event):
            state = process.GetStateFromEvent(event)
            events.append(event)
        else:
            state = lldb.eStateInvalid

    # Add events back to queue, otherwise lldb freezes
    for event in events:
        listener.AddEvent(event)

def run_command(debugger, command, result, internal_dict):
    device_app = internal_dict['fruitstrap_device_app']
    args = command.split('--',1)
    error = lldb.SBError()
    lldb.target.modules[0].SetPlatformFileSpec(lldb.SBFileSpec(device_app))
    args_arr = []
    if len(args) > 1:
        args_arr = shlex.split(args[1])
    args_arr = args_arr + shlex.split('{args}')

    launchInfo = lldb.SBLaunchInfo(args_arr)
    global listener
    launchInfo.SetListener(listener)

    #This env variable makes NSLog, CFLog and os_log messages get mirrored to stderr
    #https://stackoverflow.com/a/39581193
    launchInfo.SetEnvironmentEntries(['OS_ACTIVITY_DT_MODE=enable'], True)
    launchInfo.SetEnvironmentEntries(['DYLD_PRINT_STATISTICS_DETAILS=1'], True)
    launchInfo.SetEnvironmentEntries(['DYLD_PRINT_TO_STDERR=YES'], True)

    lldb.target.Launch(launchInfo, error)
    lockedstr = ': Locked'
    if lockedstr in str(error):
       print('\\nDevice Locked\\n')
       os._exit(254)
    else:
       print(str(error))


def waitfor_command(debugger, command, result, internal_dict):


    timetolive = {time_to_live}
    detectDeadlockTimeout = {detect_deadlock_timeout}
    printBacktraceTime = time.time() + detectDeadlockTimeout if detectDeadlockTimeout > 0 else None
    process = lldb.target.process

    threads = list()

    t0 = threading.Thread(target=setupOutput, args=(debugger, command, result, internal_dict))
    t0.deamon = True
    threads.append(t0)
    t0.start()

    run_command(debugger,command, result, internal_dict)

    t1 = threading.Thread(target=counter, args=(process, timetolive))
    t1.deamon = True
    threads.append(t1)
    t1.start()

    for i,t in enumerate(threads):
        t.join()

    state = process.GetState()
    if state == lldb.eStateExited:
        os._exit(process.GetExitStatus())
    elif printBacktraceTime is None and state == lldb.eStateStopped:
        os._exit({exitcode_app_crash})
    elif state == lldb.eStateCrashed:
        os._exit({exitcode_app_crash})
    elif state == lldb.eStateDetached:
        os._exit({exitcode_app_crash})


def counter(process, timetolive):
    background = RunInBackground(timetolive=timetolive)
    while background.canContinue:
        time.sleep(1)

    print('Run time ended, let us leave now, nothing else to see here')

    process.Stop()

def setupOutput(debugger, command, result, internal_dict):
    global listener

    process = lldb.target.process

    detectDeadlockTimeout = {detect_deadlock_timeout}
    printBacktraceTime = time.time() + detectDeadlockTimeout if detectDeadlockTimeout > 0 else None

    output_path = internal_dict['fruitstrap_output_path']

    out = None
    if output_path:
        out = open(output_path, 'a')

    def CloseOut():
        if out:
            out.close()

    while True:
        time.sleep(1)
        if process.id:
            break

    state = process.GetState()
    while state == lldb.eStateRunning:
        stdout = process.GetSTDOUT(1024)
        while stdout:
            if out:
                out.write(stdout)
            else:
                sys.stdout.write(stdout)
            stdout = process.GetSTDOUT(1024)
        state = process.GetState()

    if state == lldb.eStateExited:
        sys.stdout.write( '\\nPROCESS_EXITED\\n' )
        CloseOut()
    elif printBacktraceTime is None and state == lldb.eStateStopped:
        sys.stdout.write( '\\nPROCESS_STOPPED\\n' )
        CloseOut()
    elif state == lldb.eStateCrashed:
        sys.stdout.write( '\\nPROCESS_CRASHED\\n' )
        CloseOut()
    elif state == lldb.eStateDetached:
        sys.stdout.write( '\\nPROCESS_DETACHED\\n' )
        CloseOut()
    elif printBacktraceTime is not None and time.time() >= printBacktraceTime:
        printBacktraceTime = None
        sys.stdout.write( '\\nPRINT_BACKTRACE_TIMEOUT\\n' )
        printBacktraceTime = time.time() + 5

def safequit_command(debugger, command, result, internal_dict):
    process = lldb.target.process
    state = process.GetState()
    if state == lldb.eStateRunning:
        process.Detach()
        os._exit(0)
    elif state > lldb.eStateRunning:
        os._exit(state)
    else:
        print('\\nApplication has not been launched\\n')
        os._exit(1)


def autoexit_command(debugger, command, result, internal_dict):
    global listener
    process = lldb.target.process

    output_path = internal_dict['fruitstrap_output_path']
    out = None
    if output_path:
        out = open(output_path, 'w')

    error_path = internal_dict['fruitstrap_error_path']
    err = None
    if error_path:
        err = open(error_path, 'w')

    detectDeadlockTimeout = {detect_deadlock_timeout}
    printBacktraceTime = time.time() + detectDeadlockTimeout if detectDeadlockTimeout > 0 else None

    # This line prevents internal lldb listener from processing STDOUT/STDERR messages. Without it, an order of log writes is incorrect sometimes
    debugger.GetListener().StopListeningForEvents(process.GetBroadcaster(), lldb.SBProcess.eBroadcastBitSTDOUT | lldb.SBProcess.eBroadcastBitSTDERR )

    event = lldb.SBEvent()

    def CloseOut():
        if (out):
            out.close()
        if (err):
            err.close()

    def ProcessSTDOUT():
        stdout = process.GetSTDOUT(1024)
        while stdout:
            print(stdout)
            if out:
                out.write(stdout)
            else:
                sys.stdout.write(stdout)
            stdout = process.GetSTDOUT(1024)

    def ProcessSTDERR():
        stderr = process.GetSTDERR(1024)
        while stderr:
            if err:
                err.write(stderr)
            else:
                sys.stdout.write(stderr)
            stderr = process.GetSTDERR(1024)

    while True:
        if listener.WaitForEvent(1, event) and lldb.SBProcess.EventIsProcessEvent(event):
            state = lldb.SBProcess.GetStateFromEvent(event)
            type = event.GetType()

            if type & lldb.SBProcess.eBroadcastBitSTDOUT:
                ProcessSTDOUT()

            if type & lldb.SBProcess.eBroadcastBitSTDERR:
                ProcessSTDERR()

        else:
            state = process.GetState()

        if state != lldb.eStateRunning:
            # Let's make sure that we drained our streams before exit
            ProcessSTDOUT()
            ProcessSTDERR()

        if state == lldb.eStateExited:
            sys.stdout.write( '\\nPROCESS_EXITED\\n' )
            CloseOut()
            os._exit(process.GetExitStatus())
        elif printBacktraceTime is None and state == lldb.eStateStopped:
            sys.stdout.write( '\\nPROCESS_STOPPED\\n' )
            debugger.HandleCommand('bt')
            os._exit({exitcode_app_crash})
        elif state == lldb.eStateCrashed:
            sys.stdout.write( '\\nPROCESS_CRASHED\\n' )
            debugger.HandleCommand('bt')
            CloseOut()
            os._exit({exitcode_app_crash})
        elif state == lldb.eStateDetached:
            sys.stdout.write( '\\nPROCESS_DETACHED\\n' )
            CloseOut()
            os._exit({exitcode_app_crash})
        elif printBacktraceTime is not None and time.time() >= printBacktraceTime:
            printBacktraceTime = None
            sys.stdout.write( '\\nPRINT_BACKTRACE_TIMEOUT\\n' )
            debugger.HandleCommand('process interrupt')
            debugger.HandleCommand('bt all')
            debugger.HandleCommand('continue')
            printBacktraceTime = time.time() + 5
