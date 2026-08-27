use std::{env, fs};
use serde::Deserialize;
use rhwp::wasm_api::HwpDocument;

#[derive(Debug, Deserialize)]
#[serde(tag="op", rename_all="snake_case")]
enum Op {
    ReplacePara { sec:u32, para:u32, text:String },
    ReplaceText { sec:u32, para:u32, start:u32, len:u32, text:String },
    ReplaceAll { query:String, text:String, case_sensitive:bool },
    ReplaceCell { sec:u32, para:u32, control:u32, cell:u32, cell_para:u32, text:String },
    ReplaceCellText { sec:u32, para:u32, control:u32, cell:u32, cell_para:u32, start:u32, len:u32, text:String },
    CopyControl { sec:u32, para:u32, control:u32 },
    PasteControl { sec:u32, para:u32, offset:u32 },
    DeleteTable { sec:u32, para:u32, control:u32 },
    DeleteShape { sec:u32, para:u32, control:u32 },
    DeleteParagraph { sec:u32, para:u32 },
    InsertParagraph { sec:u32, para:u32 },
    CopySelection { sec:u32, start_para:u32, start:u32, end_para:u32, end:u32 },
    PasteInternal { sec:u32, para:u32, offset:u32 },
    SetCharShape { sec:u32, para:u32, start:u32, end:u32, char_shape:u32 },
    SetCellCharShape { sec:u32, para:u32, control:u32, cell:u32, cell_para:u32, start:u32, end:u32, char_shape:u32 },
    SetParaShape { sec:u32, para:u32, para_shape:u32 },
    SetCellParaShape { sec:u32, para:u32, control:u32, cell:u32, cell_para:u32, para_shape:u32 },
    ReflowLinesegs,
}

fn must<T>(r: Result<T, wasm_bindgen::JsValue>, what:&str) -> T {
    r.unwrap_or_else(|e| panic!("{}: {:?}", what, e))
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 3 {
        eprintln!("usage: rhwp-template-editor INPUT.hwp inspect | apply OPS.json OUTPUT.hwp");
        std::process::exit(2);
    }
    let bytes=fs::read(&args[1]).expect("read input");
    let mut doc=HwpDocument::from_bytes(&bytes).expect("parse input");
    match args[2].as_str() {
        "inspect" => {
            let sc=doc.get_section_count();
            println!("sectionCount={} pageCount={}", sc, doc.page_count());
            for s in 0..sc {
                let pc=must(doc.get_paragraph_count(s),"get_paragraph_count");
                println!("SECTION {} paragraphs={}",s,pc);
                for p in 0..pc {
                    let len=must(doc.get_paragraph_length(s,p),"get_paragraph_length");
                    let txt=must(doc.get_text_range(s,p,0,len),"get_text_range");
                    let controls=must(doc.get_control_text_positions(s,p),"get_control_text_positions");
                    println!("P{:03} len={} controls={} text={:?}",p,len,controls,txt);
                }
            }
        }
        "apply" => {
            if args.len()<5 { panic!("apply needs OPS.json OUTPUT.hwp"); }
            let ops:Vec<Op>=serde_json::from_slice(&fs::read(&args[3]).expect("read ops")).expect("parse ops");
            for (i,op) in ops.iter().enumerate() {
                let r=match op {
                    Op::ReplacePara{sec,para,text} => { let len=must(doc.get_paragraph_length(*sec,*para),"len"); doc.replace_text(*sec,*para,0,len,text) },
                    Op::ReplaceText{sec,para,start,len,text} => doc.replace_text(*sec,*para,*start,*len,text),
                    Op::ReplaceAll{query,text,case_sensitive} => doc.replace_all(query,text,*case_sensitive),
                    Op::ReplaceCell{sec,para,control,cell,cell_para,text} => {
                        let len=must(doc.get_cell_paragraph_length(*sec,*para,*control,*cell,*cell_para),"cell len");
                        must(doc.delete_text_in_cell(*sec,*para,*control,*cell,*cell_para,0,len),"delete cell");
                        doc.insert_text_in_cell(*sec,*para,*control,*cell,*cell_para,0,text)
                    },
                    Op::ReplaceCellText{sec,para,control,cell,cell_para,start,len,text} => {
                        must(doc.delete_text_in_cell(*sec,*para,*control,*cell,*cell_para,*start,*len),"delete cell range");
                        doc.insert_text_in_cell(*sec,*para,*control,*cell,*cell_para,*start,text)
                    },
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
                    Op::SetParaShape{sec,para,para_shape} => doc.set_para_shape_id(*sec,*para,*para_shape),
                    Op::SetCellParaShape{sec,para,control,cell,cell_para,para_shape} => doc.set_cell_para_shape_id(*sec,*para,*control,*cell,*cell_para,*para_shape),
                    Op::ReflowLinesegs => { let n=must(doc.reflow_linesegs(),"reflow"); Ok(format!("{{\"ok\":true,\"reflowed\":{}}}",n)) },
                };
                eprintln!("op {} {:?} => {}",i,op,must(r,"op"));
            }
            let out=doc.export_hwp_with_adapter().expect("export hwp");
            fs::write(&args[4],&out).expect("write output");
            eprintln!("WROTE {} bytes to {} pages={}",out.len(),args[4],doc.page_count());
        }
        _ => panic!("unknown mode"),
    }
}
