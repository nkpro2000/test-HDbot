import re, os, sys
import subprocess
import threading
import asyncio
import discord
import inspect
import textwrap

from typing import NewType, Sequence, Tuple, Mapping, Dict, Pattern, Union, Callable, Optional
from typing_extensions import Protocol as FnProtocol
from types import FunctionType
from functools import partial

PatternVstr = Union[Pattern,str]
UserIdentity = Union[Pattern,str,int]
UserLevel = NewType('UserLevel',int) # Admin,Member = 0,n
Msg = NewType('Msg',discord.Message)

class Fn_with_level(FnProtocol):
    def __call__(self,*groups:str,msg:Msg,level:Optional[UserLevel]=None)->Optional[str]: ...
class Fn_without_level(FnProtocol):
    def __call__(self,*groups:str,msg:Msg)->Optional[str]: ...
ExecFn = Union[Fn_with_level,Fn_without_level]

class Manager:
    """To manage all commands with the author's permission level
    """
    
    ContentFieldLimits = 2000
    
    def __init__(self,
                 P2F:Mapping[PatternVstr,ExecFn]={
                     re.compile(r'^! echo ([\s\S]*)$') : lambda *x,msg: 'Recived: '+x[0]
                     },
                 users:Optional[Dict[UserIdentity,UserLevel]]=None,
                 ):
        """To initialize and configure Manager
        Args:
            P2F = Pattern or Str to Function Map
                if Pattern matchs with message.content then Function is called with groups and msg=message
                if Str is equal to message.content then Function is called with msg=message
                in both then return string is the reply message. No reply if return value is None.
            users = Dict to get UserLevel for message.author or None
                if None then all Functions (P2F.values()) is callable by all users
                else for each Function UserLevel is checked and min level is got from Function.__kwdefaults__['level']
        """
        
        self.P2F  = P2F
        self.users = users
    
    async def on_message(self,message:Msg):
        """It have to be called on each message (client.event)
        set it in client.event like `client.event(Manager().on_message)`
        And this to just match the command with its function.
        """
        
        # Don't reply to bot's reply
        if message.author == client.user:
            return
        
        for cmd,Fn in self.P2F.items():
            if type(cmd) is str:
                if cmd == message.content:
                    response = await self.execute(Fn=Fn,msg=message)
                    if response and len(response) > self.ContentFieldLimits:
                        for response in textwrap.wrap(response,self.ContentFieldLimits):
                            await message.channel.send(response)
                    elif response:
                        await message.channel.send(response)
            else:
                match = cmd.match(message.content)
                if match:
                    response = await self.execute(*match.groups(),Fn=Fn,msg=message)
                    if response and len(response) > self.ContentFieldLimits:
                        for response in textwrap.wrap(response,self.ContentFieldLimits):
                            await message.channel.send(response)
                    elif response:
                        await message.channel.send(response)
    
    async def execute(self,*args:str,Fn:ExecFn,msg:Msg)->Optional[str]:
        """To execute the matched function, if the user has requied privileges to execute.
        It gets the required level of each function from the function's kwargument 'level'.
        Then return which Fn(*args,msg=msg) returns.
        """
        
        if Fn.__kwdefaults__ and 'level' in Fn.__kwdefaults__ and self.users != None:
            min_level = Fn.__kwdefaults__['level']
            for user,level in self.users.items():
                if type(user) is int:
                    if msg.author.id == user: break
                elif type(user) is str:
                    if msg.author.name == user: break
                else:
                    if user.match(str(msg.author)): break
            else:
                if min_level != None:
                    return ':( Not have requied permission level'
                else:
                    level = None
            if inspect.iscoroutinefunction(Fn):
                return await Fn(*args,msg=msg,level=level)
            else:
                return Fn(*args,msg=msg,level=level)
        if inspect.iscoroutinefunction(Fn):
            return await Fn(*args,msg=msg)
        else:
            return Fn(*args,msg=msg)

class Matcher:
    """To create P2F easily using decorator
    Examples:
        key = Matcher()
        @key(re.compile(r'^!\$ ([\s\S]*)$'))
        def Eval(*args,msg):
            return repr(eval(args[0],globals(),globals()))
        @key('exit')
        def Exit(*args,msg):
            exit()
        client.event(Manager(key.P2F).on_message); client.run(Token)
    """
    
    def __init__(self,P2F:Mapping[PatternVstr,ExecFn]=None):
        """
        Args:
            P2F = dict if you want to continue with previous P2F
                or None to create new one
        """
        
        self.P2F = P2F if P2F != None else dict()
    
    def __call__(self,match_with:PatternVstr)->Callable[[ExecFn],ExecFn]:
        """For saving decorated function
        """
        
        def updateP2F(Fn:ExecFn):
            self.P2F[match_with] = Fn
            return Fn
        return updateP2F

if __name__ == "__main__":
    client = discord.Client()
    @client.event
    async def on_ready():
        print(f'{client.user.name} is Online :]')
    
    key = Matcher()
    ### Python shell
    @key(re.compile(r'^!\$ ([\s\S]*)$'))
    def Exec(*args,msg):
        try:
            code = compile(args[0],'code','eval')
            global _
            _ = eval(code,globals(),globals())
            return repr(_)
        except SyntaxError:
            try:
                code = compile(args[0],'code','exec')
                exec(code,globals(),globals())
                return 'EXEC success'
            except:
                return repr(sys.exc_info())
        except:
            return repr(sys.exc_info())
    ### System shell
    processes = list()
    @key(re.compile(r'^\$ ([\s\S]*)$'))
    async def Shell(*args,msg):
        process = subprocess.Popen(args[0], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, shell=True)
        processes.append(process)
        response = list()
        threading.Thread(target=lambda p,r:r.extend(p.communicate()),args=(process,response)).start()
        while not response:
            await asyncio.sleep(.3)
        processes.remove(process)
        output, error = response[0].decode(), response[1].decode()
        outAerr = output.strip(os.linesep) + (os.linesep if error else '') + os.linesep.join([ '?>'+x for x in error.splitlines() ])
        return '$ '+args[0] + os.linesep + outAerr + os.linesep + f'Return code = {process.returncode}'
    ### To exit
    @key('!exit')
    def Exit(*args,msg):
        sys.exit(0)
    
    client.event(Manager(key.P2F).on_message)
    client.run(os.environ['DBToken'])
