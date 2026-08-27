use std::{env, fs};
use serde::Deserialize;
use serde_json::{json, Value};
use rhwp::wasm_api::HwpDocument;

#[derive(Debug, Deserialize)]
#[serde(tag="op", rename_all="snake_case")]
enum Op {
    ReplacePara { sec: usize, para: usize, text: String },
    ReplaceText { sec: usize, para: usize, start: usize, len: usize, text: String },
    ReplaceCell { sec: usize, para: usize, control: usize, cell: usize, cell_para: usize, text: String },
    ReplaceCellText { sec: usize, para: usize, control: usize, cell: usize, cell_para: usize, start: usize, len: usize, text: String },
    CopyControl { sec: usize, para: usize, control: usize },
    PasteControl { sec: usize, para: usize, offset: usize },
    DeleteTable { sec: usize, para: usize, control: usize },
    DeleteShape { sec: usize, para: usize, control: usize },
    DeleteParagraph { sec: usize, para: usize },
    InsertParagraph { sec: usize, para: usize },
    CopySelection { sec: usize, start_para: usize, start: usize, end_para: usize, end: usize },
    PasteInternal { sec: usize, para: usize, offset: usize },
    SetCharShape { sec: usize, para: usize, start: usize, end: usize, char_shape: u16 },
    SetCellCharShape { sec: usize, para: usize, control: usize, cell: usize, cell_para: usize, start: usize, end: usize, char_shape: u16 },
    ApplyChar { sec: usize, para: usize, start: usize, end: usize, props: Value },
    ApplyCellChar { sec: usize, para: usize, control: usize, cell: usize, cell_para: usize, start: usize, end: usize, props: Value },
    SetParaShape { sec: usize, para: usize, para_shape: u16 },
    SetCellParaShape { sec: usize, para: usize, control: usize, cell: usize, cell_para: usize, para_shape: u16 },
    ReflowLinesegs,
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: rhwp-template-editor INPUT.hwp inspect | apply OPS.json OUTPUT.hwp");
        std::process::exit(2);
    }
    let bytes = fs::read(&args[1]).expect("read input");
    let mut doc = HwpDocument::from_bytes(&bytes).expect("parse input");
    match args[2].as_str() {
        "inspect" => {
            let sec_count = doc.get_section_count();
            println!("{}", json!({"sectionCount":sec_count,"pageCount":doc.page_count()}));
            for s in 0..sec_count {
                let pc = doc.get_paragraph_count(s);
                println!("SECTION {} paragraphs={}", s, pc);
                for p in 0..pc {
                    let len = doc.get_paragraph_length(s,p);
                    let txt = doc.get_text_range(s,p,0,len);
                    let pos = doc.get_control_text_positions(s,p);
                    println!("P{:03} len={} controls={} text={:?}", p, len, pos, txt);
                }
            }
        }
        "apply" => {
            if args.len() < 5 { panic!("apply needs OPS.json OUTPUT.hwp"); }
            let ops: Vec<Op> = serde_json::from_slice(&fs::read(&args[3]).expect("read ops")).expect("parse ops");
            for (i,op) in ops.iter().enumerate() {
                let r = match op {
                    Op::ReplacePara{sec,para,text} => {
                        let len=doc.get_paragraph_length(*sec,*para);
                        doc.replace_text(*sec,*para,0,len,text)
                    }
                    Op::ReplaceText{sec,para,start,len,text} => doc.replace_text(*sec,*para,*start,*len,text),
                    Op::ReplaceCell{sec,para,control,cell,cell_para,text} => {
                        let len=doc.get_cell_paragraph_length(*sec,*para,*control,*cell,*cell_para);
                        let _=doc.delete_text_in_cell(*sec,*para,*control,*cell,*cell_para,0,len);
                        doc.insert_text_in_cell(*sec,*para,*control,*cell,*cell_para,0,text)
                    }
                    Op::ReplaceCellText{sec,para,control,cell,cell_para,start,len,text} => {
                        let _=doc.delete_text_in_cell(*sec,*para,*control,*cell,*cell_para,*start,*len);
                        doc.insert_text_in_cell(*sec,*para,*control,*cell,*cell_para,*start,text)
                    }
                    Op::CopyControl{sec,para,control} => doc.copy_control(*sec,*para,"",*control),
                    Op::PasteControl{sec,para,offset} => doc.paste_control(*sec,*para,*offset),
                    Op::DeleteTable{sec,para,control} => doc.delete_table_control(*sec,*para,*control),
                    Op::DeleteShape{sec,para,control} => doc.delete_shape_control(*sec,*para,*control),
                    Op::DeleteParagraph{sec,para} => doc.delete_paragraph(*sec,*para),
                    Op::InsertParagraph{sec,para} => doc.insert_paragraph(*sec,*para),
                    Op::CopySelection{sec,start_para,start,end_para,end} => doc.copy_selection(*sec,*start_para,*start,*end_para,*end),
                    Op::PasteInternal{sec,para,offset} => doc.paste_internal(*sec,*para,*offset),
                    Op::SetCharShape{sec,para,start,end,char_shape} => doc.set_char_shape_id(*sec,*para,*start,*end,*char_shape),
                    Op::SetCellCharShape{sec,para,control,cell,cell_para,start,end,char_shape} => doc.set_char_shape_id_in_cell(*sec,*para,*control,*cell,*cell_para,*start,*end,*char_shape),
                    Op::ApplyChar{sec,para,start,end,props} => doc.apply_char_format(*sec,*para,*start,*end,&props.to_string()),
                    Op::ApplyCellChar{sec,para,control,cell,cell_para,start,end,props} => doc.apply_char_format_in_cell(*sec,*para,*control,*cell,*cell_para,*start,*end,&props.to_string()),
                    Op::SetParaShape{sec,para,para_shape} => doc.set_para_shape_id(*sec,*para,*para_shape),
                    Op::SetCellParaShape{sec,para,control,cell,cell_para,para_shape} => doc.set_cell_para_shape_id(*sec,*para,*control,*cell,*cell_para,*para_shape),
                    Op::ReflowLinesegs => { let n=doc.reflow_linesegs(); json!({"ok":true,"reflowed":n}).to_string() },
                };
                eprintln!("op {} {:?} => {}",i,op,r);
            }
            let out = doc.export_hwp_with_adapter().expect("export hwp");
            fs::write(&args[4], &out).expect("write output");
            eprintln!("WROTE {} bytes to {} pages={}",out.len(),args[4],doc.page_count());
        }
        _ => panic!("unknown mode"),
    }
}
