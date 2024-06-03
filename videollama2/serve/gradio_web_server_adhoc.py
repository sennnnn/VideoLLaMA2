import os
import shutil
import subprocess

import torch
import tempfile
import gradio as gr
from PIL import Image
from fastapi import FastAPI
from decord import VideoReader, cpu
from transformers import TextStreamer

import sys
sys.path.append('./')
from videollama2.constants import MMODAL_TOKEN_INDEX, DEFAULT_MMODAL_TOKEN
from videollama2.conversation import conv_templates, SeparatorStyle, Conversation
from videollama2.model.builder import load_pretrained_model
from videollama2.mm_utils import KeywordsStoppingCriteria, tokenizer_MMODAL_token, get_model_name_from_path, process_image, process_video


title_markdown = ("""
<div style="display: flex; justify-content: center; align-items: center; text-align: center;">
  <a href="https://github.com/DAMO-NLP-SG/VideoLLaMA2" style="margin-right: 20px; text-decoration: none; display: flex; align-items: center;">
    <img src="https://s2.loli.net/2024/06/03/D3NeXHWy5az9tmT.png" alt="VideoLLaMA2🚀" style="max-width: 120px; height: auto;">
  </a>
  <div>
    <h1 >VideoLLaMA 2: Advancing Spatial-Temporal Modeling and Audio Understanding in Video-LLMs</h1>
    <h5 style="margin: 0;">If you like our project, please give us a star ✨ on Github for the latest update.</h5>
  </div>
</div>


<div align="center">
    <div style="display:flex; gap: 0.25rem;" align="center">
        <a href='VideoLLaMA 2: Advancing Spatial-Temporal Modeling and Audio Understanding in Video-LLMs'><img src='https://img.shields.io/badge/Github-Code-blue'></a>
        <a href="https://arxiv.org/pdf/2406.xxxxx.pdf"><img src="https://img.shields.io/badge/Arxiv-2406.xxxxx-red"></a>
        <a href='https://github.com/DAMO-NLP-SG/VideoLLaMA2/stargazers'><img src='https://img.shields.io/github/stars/DAMO-NLP-SG/VideoLLaMA2.svg?style=social'></a>
    </div>
</div>
""")


block_css = """
#buttons button {
    min-width: min(120px,100%);
}
"""


tos_markdown = ("""
### Terms of use
By using this service, users are required to agree to the following terms:
The service is a research preview intended for non-commercial use only. It only provides limited safety measures and may generate offensive content. It must not be used for any illegal, harmful, violent, racist, or sexual purposes. The service may collect user dialogue data for future research.
Please click the "Flag" button if you get any inappropriate answer! We will collect those to keep improving our moderator.
For an optimal experience, please use desktop computers for this demo, as mobile devices may compromise its quality.
""")


learn_more_markdown = ("""
### License
The service is a research preview intended for non-commercial use only, subject to the model [License](https://github.com/facebookresearch/llama/blob/main/MODEL_CARD.md) of LLaMA, [Terms of Use](https://openai.com/policies/terms-of-use) of the data generated by OpenAI, and [Privacy Practices](https://chrome.google.com/webstore/detail/sharegpt-share-your-chatg/daiacboceoaocpibfodeljbdfacokfjb) of ShareGPT. Please contact us if you find any potential violation.
""")


class Chat:
    def __init__(self, model_path, conv_mode, model_base=None, load_8bit=False, load_4bit=False, device='cuda'):
        # disable_torch_init()
        model_name = get_model_name_from_path(model_path)
        self.tokenizer, self.model, processor, context_len = load_pretrained_model(
            model_path, model_base, model_name,
            load_8bit, load_4bit,
            device=device)
        self.processor = processor
        self.conv_mode = conv_mode
        self.conv = conv_templates[conv_mode].copy()
        self.device = self.model.device

    def get_prompt(self, qs, state):
        state.append_message(state.roles[0], qs)
        state.append_message(state.roles[1], None)
        return state

    @torch.inference_mode()
    def generate(self, tensor: list, modals: list, prompt: str, first_run: bool, state):
        assert len(tensor) == len(modals) == 1

        # 1. prepare model, tokenizer, and processor.
        tokenizer, model, processor = self.tokenizer, self.model, self.processor

        # 2. text preprocess (tag process & generate prompt).
        state = self.get_prompt(prompt, state)
        prompt = state.get_prompt()
        # print('\n\n\n')
        # print(prompt)
        input_ids = tokenizer_MMODAL_token(prompt, tokenizer, MMODAL_TOKEN_INDEX[modals[0]], return_tensors='pt').unsqueeze(0).to(self.device)

        # 3. generate response according to visual signals and prompts. 
        stop_str = self.conv.sep if self.conv.sep_style in [SeparatorStyle.SINGLE] else self.conv.sep2
        # keywords = ["<s>", "</s>"]
        keywords = [stop_str]
        stopping_criteria = KeywordsStoppingCriteria(keywords, tokenizer, input_ids)

        with torch.inference_mode():
            output_ids = model.generate(
                input_ids,
                images_or_videos=tensor,
                modal_list=modals,
                do_sample=True,
                temperature=0.2,
                max_new_tokens=1024,
                use_cache=True,
                stopping_criteria=[stopping_criteria],
            )

        outputs = tokenizer.batch_decode(output_ids, skip_special_tokens=True)[0]
        print(outputs)
        return outputs, state


def save_image_to_local(image):
    filename = os.path.join('temp', next(tempfile._get_candidate_names()) + '.jpg')
    image = Image.open(image)
    image.save(filename)
    return filename


def save_video_to_local(video_path):
    filename = os.path.join('temp', next(tempfile._get_candidate_names()) + '.mp4')
    shutil.copyfile(video_path, filename)
    return filename


def generate(image, video, textbox_in, first_run, state, state_, tensor, modals):
    flag = 1
    if not textbox_in:
        if len(state_.messages) > 0:
            textbox_in = state_.messages[-1][1]
            state_.messages.pop(-1)
            flag = 0
        else:
            return "Please enter instruction"

    image = image if image else "none"
    video = video if video else "none"
    assert not (os.path.exists(image) and os.path.exists(video))

    if type(state) is not Conversation:
        state = conv_templates[conv_mode].copy()
        state_ = conv_templates[conv_mode].copy()
        tensor = []
        modals = []

    first_run = False if len(state.messages) > 0 else True

    text_en_in = textbox_in.replace("picture", "image")

    processor = handler.processor
    if os.path.exists(image) and not os.path.exists(video):
        tensor.append(process_image(image, processor).to(handler.model.device, dtype=dtype))
        modals.append('IMAGE')
    if not os.path.exists(image) and os.path.exists(video):
        tensor.append(process_video(video, processor).to(handler.model.device, dtype=dtype))
        modals.append('VIDEO')
    if os.path.exists(image) and os.path.exists(video):
        raise NotImplementedError("Not support image and video at the same time")

    if os.path.exists(image) and not os.path.exists(video):
        text_en_in = DEFAULT_MMODAL_TOKEN['IMAGE'] + '\n' + text_en_in
    if not os.path.exists(image) and os.path.exists(video):
        text_en_in = DEFAULT_MMODAL_TOKEN['VIDEO'] + '\n' + text_en_in
    # if os.path.exists(image) and os.path.exists(video):
    #   pass
    text_en_out, state_ = handler.generate(tensor, modals, text_en_in, first_run=first_run, state=state_)
    state_.messages[-1] = (state_.roles[1], text_en_out)

    text_en_out = text_en_out.split('#')[0]
    textbox_out = text_en_out

    show_images = ""
    if os.path.exists(image):
        filename = save_image_to_local(image)
        show_images += f'<img src="./file={filename}" style="display: inline-block;width: 250px;max-height: 400px;">'
    if os.path.exists(video):
        filename = save_video_to_local(video)
        show_images += f'<video controls playsinline width="500" style="display: inline-block;"  src="./file={filename}"></video>'

    if flag:
        state.append_message(state.roles[0], textbox_in + "\n" + show_images)
    state.append_message(state.roles[1], textbox_out)

    return (state, state_, state.to_gradio_chatbot(), False, gr.update(value=None, interactive=True), tensor, modals, gr.update(value=image if os.path.exists(image) else None, interactive=True), gr.update(value=video if os.path.exists(video) else None, interactive=True))


def regenerate(state, state_):
    state.messages.pop(-1)
    state_.messages.pop(-1)
    if len(state.messages) > 0:
        return state, state_, state.to_gradio_chatbot(), False
    return (state, state_, state.to_gradio_chatbot(), True)


def clear_history(state, state_):
    state = conv_templates[conv_mode].copy()
    state_ = conv_templates[conv_mode].copy()
    return (gr.update(value=None, interactive=True),
            gr.update(value=None, interactive=True), \
            gr.update(value=None, interactive=True), \
            True, state, state_, state.to_gradio_chatbot(), [], [])


conv_mode = "llama_2"
model_path = 'publish_models/videollama2-ep3'
device = 'cuda'
load_8bit = True
load_4bit = False
dtype = torch.float16
handler = Chat(model_path, conv_mode=conv_mode, load_8bit=load_8bit, load_4bit=load_8bit, device=device)
# handler.model.to(dtype=dtype)
if not os.path.exists("temp"):
    os.makedirs("temp")

app = FastAPI()


textbox = gr.Textbox(
    show_label=False, placeholder="Enter text and press ENTER", container=False
)
with gr.Blocks(title='VideoLLaMA2🚀', theme=gr.themes.Default(), css=block_css) as demo:
    gr.Markdown(title_markdown)
    state = gr.State()
    state_ = gr.State()
    first_run = gr.State()
    tensor = gr.State()
    modals = gr.State()

    with gr.Row():
        with gr.Column(scale=3):
            image = gr.Image(label="Input Image", type="filepath")
            video = gr.Video(label="Input Video")

            cur_dir = os.path.dirname(os.path.abspath(__file__))
            gr.Examples(
                examples=[
                    [
                        f"{cur_dir}/examples/extreme_ironing.jpg",
                        "What is unusual about this image?",
                    ],
                    [
                        f"{cur_dir}/examples/waterview.jpg",
                        "What are the things I should be cautious about when I visit here?",
                    ],
                    [
                        f"{cur_dir}/examples/desert.jpg",
                        "If there are factual errors in the questions, point it out; if not, proceed answering the question. What’s happening in the desert?",
                    ],
                ],
                inputs=[image, textbox],
            )

        with gr.Column(scale=7):
            chatbot = gr.Chatbot(label="VideoLLaMA2", bubble_full_width=True).style(height=750)
            with gr.Row():
                with gr.Column(scale=8):
                    textbox.render()
                with gr.Column(scale=1, min_width=50):
                    submit_btn = gr.Button(value="Send", variant="primary", interactive=True)
            with gr.Row(elem_id="buttons") as button_row:
                upvote_btn = gr.Button(value="👍  Upvote", interactive=True)
                downvote_btn = gr.Button(value="👎  Downvote", interactive=True)
                flag_btn = gr.Button(value="⚠️  Flag", interactive=True)
                # stop_btn = gr.Button(value="⏹️  Stop Generation", interactive=False)
                regenerate_btn = gr.Button(value="🔄  Regenerate", interactive=True)
                clear_btn = gr.Button(value="🗑️  Clear history", interactive=True)

    # with gr.Row():
    #     gr.Examples(
    #         examples=[
    #             [
    #                 f"{cur_dir}/examples/sample_img_22.png",
    #                 f"{cur_dir}/examples/sample_demo_22.mp4",
    #                 "Are the instruments in the pictures used in the video?",
    #             ],
    #             [
    #                 f"{cur_dir}/examples/sample_img_13.png",
    #                 f"{cur_dir}/examples/sample_demo_13.mp4",
    #                 "Does the flag in the image appear in the video?",
    #             ],
    #             [
    #                 f"{cur_dir}/examples/sample_img_8.png",
    #                 f"{cur_dir}/examples/sample_demo_8.mp4",
    #                 "Are the image and the video depicting the same place?",
    #             ],
    #         ],
    #         inputs=[image, video, textbox],
    #     )
    #     gr.Examples(
    #         examples=[
    #             [
    #                 f"{cur_dir}/examples/sample_demo_1.mp4",
    #                 "Why is this video funny?",
    #             ],
    #             [
    #                 f"{cur_dir}/examples/sample_demo_3.mp4",
    #                 "Can you identify any safety hazards in this video?"
    #             ],
    #             [
    #                 f"{cur_dir}/examples/sample_demo_9.mp4",
    #                 "Describe the video.",
    #             ],
    #             [
    #                 f"{cur_dir}/examples/sample_demo_22.mp4",
    #                 "Describe the activity in the video.",
    #             ],
    #         ],
    #         inputs=[video, textbox],
    #     )
    gr.Markdown(tos_markdown)
    gr.Markdown(learn_more_markdown)

    submit_btn.click(generate, [image, video, textbox, first_run, state, state_, tensor, modals],
                     [state, state_, chatbot, first_run, textbox, tensor, modals, image, video])

    regenerate_btn.click(regenerate, [state, state_], [state, state_, chatbot, first_run]).then(
        generate, [image, video, textbox, first_run, state, state_, tensor, modals], [state, state_, chatbot, first_run, textbox, tensor, modals, image, video])

    clear_btn.click(clear_history, [state, state_],
                    [image, video, textbox, first_run, state, state_, chatbot, tensor, modals])

# app = gr.mount_gradio_app(app, demo, path="/")
demo.launch(share=True)

# uvicorn videollama2.serve.gradio_web_server:app
# python -m videollama2.serve.gradio_web_server
