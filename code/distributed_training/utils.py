import time
import torch
from dataset.dataset_collection import DatasetCollection
import torchvision.transforms as transforms
import torch.utils.data.distributed
import torch.nn.functional as F
import torch.distributed as dist
import torch.distributed as dist
from distributed_layers import ForwardSend_BackwardReceive,ForwardReceive_BackwardSend,generate_recv


def prepare_dataloader(normalize, compose_train, compose_val, args):
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225])

    dataset_collection = DatasetCollection(
        args.dataset_type, args.data, compose_train, compose_val)
    train_dataset, val_dataset = dataset_collection.init()


    train_sampler = None

    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True,
        num_workers=args.workers, pin_memory=True, sampler=train_sampler)

    val_loader = torch.utils.data.DataLoader(
        val_dataset,
        batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=True)
    return train_sampler, train_loader, val_loader


def train_header(rank,model,optimizer,train_loader,criterion,args):
    # print("Use GPU",rank, "as the first part")
    model.train()
    batch_time_avg = 0.0
    data_time_avg = 0.0
    acc1_avg = 0.0
    loss_avg = 0.0
    start = time.time()
    for i, (images, targets) in enumerate(train_loader):
        # print("rank:",rank,"i:",i,"begin")
        # for j in range(args.world_size):
        #     dist.send(torch.tensor(targets[0]))
        targets = targets.cuda(rank, non_blocking=True)
        # targets = ForwardSend_BackwardReceive.apply(targets,args.world_size-1,args.world_size-1,rank)
        data_time = time.time() -start
        images = images.cuda(rank, non_blocking=True)
        output = model(images)
        output = ForwardSend_BackwardReceive.apply(output,rank+1,rank+1,rank)
        # optimizer.zero_grad()
        # recv_size = output.clone().detach()
        # output.backward(recv_size)
        # optimizer.step()
        label = generate_recv(args.world_size-1,rank)
        label = ForwardReceive_BackwardSend.apply(label,args.world_size-1,args.world_size-1,rank)
        loss = criterion(label,targets)
        loss.backward()
        optimizer.zero_grad()
        recv_size = output.clone().detach()
        output.backward(recv_size)
        optimizer.step()
        batch_time = time.time() - start
        acc1, acc5 = accuracy(label, targets, topk=(1, 5))
        batch_time_avg = batch_time_avg + batch_time
        data_time_avg = data_time_avg + data_time
        loss_avg = loss_avg + loss
        if i % 30 == 0:
            print("train_loss:",loss,"train_acc1",acc1)
        acc1_avg = acc1 + acc1_avg
        start = time.time()
    batch_time_avg = batch_time_avg / len(train_loader)
    data_time_avg =data_time_avg / len(train_loader)
    acc1_avg = acc1_avg / len(train_loader)
    loss_avg =loss_avg / len(train_loader)
    #TODO loss
    return batch_time_avg,data_time_avg,acc1_avg,loss_avg


def val_header(rank,model,val_loader,criterion,args):
    model.eval()
    batch_time_avg = 0.0
    data_time_avg = 0.0
    acc1_avg = 0.0
    loss_avg = 0.0
    #for i 
    with torch.no_grad():
        end = time.time()
        for i,(images,target) in enumerate(val_loader):
            images = images.cuda(rank, non_blocking = True)
            target = target.cuda(rank, non_blocking=True)
            output = model(images)
            output = ForwardSend_BackwardReceive.apply(output,rank+1,rank+1,rank)
            label = generate_recv(args.world_size-1,rank)
            label = ForwardReceive_BackwardSend.apply(label,args.world_size-1,args.world_size-1,rank)
            loss = criterion(label,target)
            acc1, acc5 = accuracy(label, target, topk=(1, 5))
            batch_time = time.time() - end
            end = time.time()
            batch_time_avg = batch_time_avg + batch_time
            loss_avg = loss_avg + loss
            acc1_avg = acc1_avg + acc1
            if i%30 == 0:
                print("train_loss:",loss,"train_acc1",acc1)
    batch_time_avg = batch_time_avg / len(val_loader)
    acc1_avg = acc1_avg / len(val_loader)
    loss_avg =loss_avg / len(val_loader)
    return batch_time_avg,acc1_avg,loss_avg




    
def train_medium(rank,model,optimizer,iter_time,args):
    # print("Use GPU",rank, "as the medium part")
    model.train()
    batch_time_avg = 0.0
    data_time_avg = 0.0
    start = time.time()
    for i in range(iter_time):
        # print("rank:",rank,"i:",i,"begin")
        data_time = time.time() -start
        input = generate_recv(rank-1,rank)
        input = ForwardReceive_BackwardSend.apply(input,rank-1,rank-1,rank)
        output = model(input)
        output = ForwardSend_BackwardReceive.apply(output,rank+1,rank+1,rank)
        optimizer.zero_grad()
        recv_size = output.clone().detach()
        output.backward(recv_size)
        optimizer.step()
        batch_time = time.time() - start
        
        batch_time_avg = batch_time_avg + batch_time
        data_time_avg = data_time_avg + data_time
        start = time.time()
    batch_time_avg = batch_time_avg / iter_time
    data_time_avg =data_time_avg / iter_time
    return batch_time_avg,data_time_avg
    pass

def val_medium(rank,model,iter_time,args):
    batch_time_avg = 0.0
    model.eval()
    with torch.no_grad():
        end = time.time()
        for i in range(iter_time):
            input = generate_recv(rank-1,rank)
            input = ForwardReceive_BackwardSend.apply(input,rank-1,rank-1,rank)
            output = model(input)
            output = ForwardSend_BackwardReceive.apply(output,rank+1,rank+1,rank)
            batch_time = time.time() - end
            end = time.time()
            batch_time_avg = batch_time_avg + batch_time
        batch_time_avg = batch_time_avg / iter_time
        return batch_time_avg





def train_last(rank,model,optimizer,iter_time,args):
    # print("Use GPU",rank, "as the last part")
    model.train()
    batch_time_avg = 0.0
    data_time_avg = 0.0
    start = time.time()
    for i in range(iter_time):
        # print("rank:",rank,"i:",i,"begin")
        # target = generate_recv(0,rank)
        # target = ForwardReceive_BackwardSend.apply(target,0,0,rank)
        # target = target.type(torch.int64)
        data_time = time.time() -start
        input = generate_recv(rank-1,rank)
        input = ForwardReceive_BackwardSend.apply(input,rank-1,rank-1,rank)
        output = model(input)
        output = ForwardSend_BackwardReceive.apply(output,0,0,rank)
        # loss = criterion(output,target)
        # acc1, acc5 = accuracy(output, target, topk=(1, 5))
        recv = output.clone().detach()
        optimizer.zero_grad()
        output.backward(recv)
        optimizer.step()
        batch_time = time.time() - start
        batch_time_avg = batch_time_avg + batch_time
        data_time_avg = data_time_avg + data_time
        # acc1_avg = acc1 + acc1_avg
        # if i% 30 == 0:
        #     print("loss:",loss,"acc1",acc1)
        start = time.time()
    batch_time_avg = batch_time_avg / iter_time
    data_time_avg =data_time_avg / iter_time
    return batch_time_avg,data_time_avg

def val_last(rank,model,iter_time,args):
    model.eval()
    batch_time_avg = 0.0
    with torch.no_grad():
        end = time.time()
        for i in range(iter_time):
            
            input = generate_recv(rank-1,rank)
            input = ForwardReceive_BackwardSend.apply(input,rank-1,rank-1,rank)
            output = model(input)
            output = ForwardSend_BackwardReceive.apply(output,0,0,rank)
            batch_time = time.time() -end
            end = time.time()
            batch_time_avg = batch_time_avg + batch_time
        batch_time_avg = batch_time_avg / iter_time
        return batch_time_avg




def accuracy(output, target, topk=(1,)):
    """Computes the accuracy over the k top predictions for the specified values of k"""
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)

        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))

        res = []
        for k in topk:
            correct_k = correct[:k].reshape(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res